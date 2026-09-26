import os
import re
import time
import uuid
import hashlib
import sqlite3

import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue, PayloadSchemaType,
)

from services.rag import get_qdrant, get_embeddings

JUDGMENTS_DATA_PATH = os.getenv("JUDGMENTS_DATA_PATH", "./data/judgments")
JUDGMENTS_COLLECTION_NAME = "judgments"
VECTOR_SIZE = 384

HF_REPO_ID = "vaquill/open-india-law"
HF_REPO_TYPE = "dataset"
HF_TOKEN = os.getenv("HF_TOKEN")

# Fallback order per S1 brief: (a) SC + top HCs, last 15y -> (b) SC only, all years
# -> (c) SC only, last 10y. MAX_CHILD_CHUNKS bounds how much we embed in one day on CPU
# AND bounds peak memory during ingestion — court parquet files are multi-GB and this
# machine has limited RAM, so rows are streamed+filtered in row-group batches (see
# _stream_filtered) rather than loaded whole via pd.read_parquet, which OOM-killed the
# process on a first attempt.
MAX_CHILD_CHUNKS = int(os.getenv("JUDGMENTS_MAX_CHUNKS", "150000"))
_PARQUET_BATCH_SIZE = 20000

# The dataset carries machine-translated duplicates of most judgments (language_code:
# pun/hin/guj/tam/... alongside en) — only ~36% of rows in the SC last-10y window are
# English. FastEmbed's bge-small-en-v1.5 is English-only, so untranslated-language rows
# would embed to near-meaningless vectors and dilute retrieval. Filtered at ingestion.
LANGUAGE_FILTER = os.getenv("JUDGMENTS_LANGUAGE", "en")

SUPREME_COURT_FILE = "in_supreme-court_judgments.parquet"
TOP_HIGH_COURT_FILES = [
    ("delhi", "in_delhi_judgments.parquet"),
    ("bombay", "in_bombay_judgments.parquet"),
    ("madras", "in_madras_judgments.parquet"),
    ("calcutta", "in_calcutta_judgments.parquet"),
]

# Real schema, confirmed against the dataset's own datasets-server API (vaquill/open-india-law
# has NO paragraph_number field — it chunks by semantic section_type, not court paragraph
# numbering, contrary to the original brief's assumption). See ingest_judgments docstring.
# text_original is deliberately excluded — it roughly doubles per-row text memory and this
# ingestion already runs tight on RAM; paragraph numbers are extracted from `text` instead.
PARQUET_COLUMNS = [
    "case_id", "chunk_id", "chunk_index", "total_chunks",
    "text", "char_start", "char_end", "page_start", "page_end",
    "section_type", "court", "court_type",
    "title", "petitioner", "respondent", "disposition", "citation",
    "decision_date", "year", "language_code",
]

# Best-effort extraction of court-numbered paragraphs (e.g. "12. Learned counsel submits...")
# from the raw judgment text. The source dataset has no paragraph_number field, so this is a
# heuristic, not authoritative — see ingest_judgments docstring for why.
PARAGRAPH_NUMBER_PATTERN = re.compile(r"(?m)^\s{0,3}(\d{1,4})\.\s+(?=[A-Z(\"'])")


def _extract_paragraph_numbers(text: str) -> list:
    if not text:
        return []
    numbers = []
    for m in PARAGRAPH_NUMBER_PATTERN.findall(text):
        n = int(m)
        if 0 < n < 2000:  # sanity bound against false positives (dates, citations, etc.)
            numbers.append(n)
    return numbers


def ensure_judgments_collection():
    client = get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if JUDGMENTS_COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=JUDGMENTS_COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    for field_name in ("court", "case_id", "year"):
        try:
            client.create_payload_index(
                collection_name=JUDGMENTS_COLLECTION_NAME,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD if field_name != "year" else PayloadSchemaType.INTEGER,
            )
        except Exception:
            pass


def get_judgments_collection_count() -> int:
    try:
        ensure_judgments_collection()
        return get_qdrant().count(collection_name=JUDGMENTS_COLLECTION_NAME).count
    except Exception:
        return 0


def _parents_db_path() -> str:
    path = os.path.join(JUDGMENTS_DATA_PATH, "parents.db")
    if not os.path.exists(path):
        os.makedirs(JUDGMENTS_DATA_PATH, exist_ok=True)
        try:
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS judgments (
                    case_id TEXT PRIMARY KEY,
                    case_name TEXT,
                    court TEXT,
                    date TEXT,
                    citation TEXT,
                    disposition TEXT,
                    full_text TEXT,
                    chunk_count INTEGER
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[JudgmentSearch] Failed to init parents.db: {e}")
    return path


def _init_parents_db() -> sqlite3.Connection:
    os.makedirs(JUDGMENTS_DATA_PATH, exist_ok=True)
    conn = sqlite3.connect(_parents_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS judgments (
            case_id TEXT PRIMARY KEY,
            case_name TEXT,
            court TEXT,
            date TEXT,
            citation TEXT,
            disposition TEXT,
            full_text TEXT,
            chunk_count INTEGER
        )
    """)
    conn.commit()
    return conn


def get_parent_judgment(case_id: str) -> dict:
    try:
        from models.database import SessionLocal, Judgment
        db = SessionLocal()
        try:
            j = db.query(Judgment).filter(Judgment.case_id == case_id).first()
            if j:
                return {
                    "case_id": j.case_id,
                    "case_name": j.case_name,
                    "court": j.court,
                    "date": j.date,
                    "citation": j.citation,
                    "disposition": j.disposition,
                    "full_text": j.full_text,
                    "chunk_count": j.chunk_count,
                }
        finally:
            db.close()
    except Exception as e:
        print(f"[JudgmentSearch] PostgreSQL lookup notice: {e}")

    try:
        conn = sqlite3.connect(_parents_db_path())
        try:
            row = conn.execute(
                "SELECT case_id, case_name, court, date, citation, disposition, full_text, chunk_count "
                "FROM judgments WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {
            "case_id": row[0],
            "case_name": row[1],
            "court": row[2],
            "date": row[3],
            "citation": row[4],
            "disposition": row[5],
            "full_text": row[6],
            "chunk_count": row[7],
        }
    except Exception as e:
        print(f"[JudgmentSearch] get_parent_judgment failed: {e}")
        return None


def search_by_case_id(case_id: str) -> dict | None:
    return get_parent_judgment(case_id)


def search_by_exact_citation(citation_str: str) -> dict | None:
    if not citation_str or not citation_str.strip():
        return None
    try:
        conn = sqlite3.connect(_parents_db_path())
        try:
            row = conn.execute(
                "SELECT case_id, case_name, court, date, citation, disposition, full_text, chunk_count "
                "FROM judgments WHERE citation = ? OR citation LIKE ? LIMIT 1",
                (citation_str.strip(), f"%{citation_str.strip()}%"),
            ).fetchone()
        finally:
            conn.close()
        if row:
            return {
                "case_id": row[0], "case_name": row[1], "court": row[2],
                "date": row[3], "citation": row[4], "disposition": row[5],
                "full_text": row[6], "chunk_count": row[7],
                "resolution_method": "exact_citation",
            }
    except Exception as e:
        print(f"[JudgmentSearch] search_by_exact_citation failed: {e}")
    return None


def search_by_normalized_citation(norm_cit: str) -> dict | None:
    if not norm_cit:
        return None
    try:
        conn = sqlite3.connect(_parents_db_path())
        try:
            rows = conn.execute("SELECT case_id, case_name, court, date, citation, disposition, full_text, chunk_count FROM judgments WHERE citation != ''").fetchall()
        finally:
            conn.close()
        from services.citation_parser import normalize_citation_string
        for row in rows:
            if normalize_citation_string(row[4]) == norm_cit:
                return {
                    "case_id": row[0], "case_name": row[1], "court": row[2],
                    "date": row[3], "citation": row[4], "disposition": row[5],
                    "full_text": row[6], "chunk_count": row[7],
                    "resolution_method": "normalized_citation",
                }
    except Exception as e:
        print(f"[JudgmentSearch] search_by_normalized_citation failed: {e}")
    return None


def search_by_case_name_and_year(case_name: str, year: int = None, court: str = None) -> dict | None:
    if not case_name:
        return None
    try:
        conn = sqlite3.connect(_parents_db_path())
        try:
            rows = conn.execute("SELECT case_id, case_name, court, date, citation, disposition, full_text, chunk_count FROM judgments").fetchall()
        finally:
            conn.close()
        from services.citation_parser import calculate_name_similarity
        best_row, best_sim = None, 0.0
        for row in rows:
            r_name = row[1]
            r_date = row[3]
            r_year = int(r_date[:4]) if r_date and len(r_date) >= 4 and r_date[:4].isdigit() else None
            if year and r_year and abs(year - r_year) > 2:
                continue
            sim = calculate_name_similarity(case_name, r_name)
            if sim > best_sim:
                best_sim, best_row = sim, row

        if best_row and best_sim >= 0.65:
            return {
                "case_id": best_row[0], "case_name": best_row[1], "court": best_row[2],
                "date": best_row[3], "citation": best_row[4], "disposition": best_row[5],
                "full_text": best_row[6], "chunk_count": best_row[7],
                "resolution_method": "exact_case_name_and_year" if year else "normalized_case_name",
                "_name_match_score": best_sim,
            }
    except Exception as e:
        print(f"[JudgmentSearch] search_by_case_name_and_year failed: {e}")
    return None


def resolve_internal_case_identity(parsed: dict) -> dict | None:
    """STAGE 1: Resolve citation identity in the internal corpus using strict priority.
    Priority:
    A. exact citation
    B. normalized citation
    C. neutral citation
    D. canonical case ID
    E. exact case-name + court + year
    F. alternate case-name normalization
    DO NOT use semantic similarity as an identity signal.
    """
    cit_str = parsed.get("citation_string", "")
    norm_cit = parsed.get("normalized_citation", "")
    neutral = parsed.get("neutral_citation", "")
    case_name = parsed.get("case_name", "")
    year = parsed.get("year")
    court = parsed.get("court")

    # Priority A: exact citation
    if cit_str:
        res = search_by_exact_citation(cit_str)
        if res:
            return res

    # Priority B: normalized citation
    if norm_cit:
        res = search_by_normalized_citation(norm_cit)
        if res:
            return res

    # Priority C: neutral citation
    if neutral:
        res = search_by_exact_citation(neutral)
        if res:
            res["resolution_method"] = "neutral_citation"
            return res

    # Priority E & F: Case name + year / normalization
    if case_name:
        res = search_by_case_name_and_year(case_name, year=year, court=court)
        if res:
            return res

    return None




def _download_court_file(filename: str) -> str:
    print(f"[JudgmentSearch] Downloading {filename} from {HF_REPO_ID}...", flush=True)
    return hf_hub_download(
        repo_id=HF_REPO_ID,
        repo_type=HF_REPO_TYPE,
        filename=filename,
        cache_dir=os.path.join(JUDGMENTS_DATA_PATH, "hf_cache"),
        token=HF_TOKEN,
    )


def _stream_filtered(path: str, cutoff_date=None, row_cap=None) -> tuple:
    """
    Read a court parquet file in row-group batches (pyarrow) rather than via pd.read_parquet,
    which materializes the entire file in memory at once — these files are multi-GB and this
    ingestion runs on a memory-constrained machine, so a whole-file read reliably OOM-kills the
    process. Filters by decision_date and stops once row_cap rows have been collected.

    Returns (dataframe, hit_cap) — hit_cap is True if we stopped early because of row_cap,
    meaning the returned set is a partial (non-exhaustive) slice of what matches cutoff_date.
    """
    pf = pq.ParquetFile(path)
    collected = []
    total = 0
    hit_cap = False

    for batch in pf.iter_batches(columns=PARQUET_COLUMNS, batch_size=_PARQUET_BATCH_SIZE):
        df = batch.to_pandas()
        if LANGUAGE_FILTER:
            df = df[df["language_code"] == LANGUAGE_FILTER]
        if df.empty:
            continue
        df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce", utc=True).dt.tz_localize(None)
        if cutoff_date is not None:
            df = df[df["decision_date"] >= cutoff_date]
        if df.empty:
            continue

        if row_cap is not None and total + len(df) > row_cap:
            df = df.head(row_cap - total)
            hit_cap = True

        collected.append(df)
        total += len(df)

        if row_cap is not None and total >= row_cap:
            break

    if not collected:
        return pd.DataFrame(columns=PARQUET_COLUMNS), False
    return pd.concat(collected, ignore_index=True), hit_cap


def _load_filtered_corpus():
    """Follow the S1 fallback order empirically, bounded by MAX_CHILD_CHUNKS."""
    now = pd.Timestamp.utcnow().tz_localize(None)
    cutoff_15y = now - pd.DateOffset(years=15)
    cutoff_10y = now - pd.DateOffset(years=10)

    sc_path = _download_court_file(SUPREME_COURT_FILE)

    # Attempt (a): Supreme Court + top High Courts, last 15 years
    sc_df_15y, sc_hit_cap = _stream_filtered(sc_path, cutoff_date=cutoff_15y, row_cap=MAX_CHILD_CHUNKS)

    if not sc_hit_cap and len(sc_df_15y) < MAX_CHILD_CHUNKS:
        combined = [sc_df_15y]
        total_rows = len(sc_df_15y)
        included_courts = ["supreme-court"]

        for court_key, filename in TOP_HIGH_COURT_FILES:
            if total_rows >= MAX_CHILD_CHUNKS:
                break
            try:
                hc_path = _download_court_file(filename)
            except Exception as e:
                print(f"[JudgmentSearch] Skipping {filename}: {e}")
                continue
            hc_df, _ = _stream_filtered(hc_path, cutoff_date=cutoff_15y, row_cap=MAX_CHILD_CHUNKS - total_rows)
            combined.append(hc_df)
            total_rows += len(hc_df)
            included_courts.append(court_key)

        if len(included_courts) > 1:
            df = pd.concat(combined, ignore_index=True)
            label = f"Supreme Court + {', '.join(included_courts[1:])}, last 15 years ({total_rows} rows)"
            return df, label

    # Attempt (b): Supreme Court only, all years (bounded by MAX_CHILD_CHUNKS regardless)
    sc_df_all, all_hit_cap = _stream_filtered(sc_path, cutoff_date=None, row_cap=MAX_CHILD_CHUNKS)
    if not all_hit_cap:
        return sc_df_all, f"Supreme Court only, all years ({len(sc_df_all)} rows)"

    # Attempt (c): Supreme Court only, last 10 years (capped to budget if still too large)
    sc_df_10y, y10_hit_cap = _stream_filtered(sc_path, cutoff_date=cutoff_10y, row_cap=MAX_CHILD_CHUNKS)
    suffix = ", capped to budget" if y10_hit_cap else ""
    return sc_df_10y, f"Supreme Court only, last 10 years{suffix} ({len(sc_df_10y)} rows)"


def ingest_judgments(stream_batch_size: int = 128, force: bool = False):
    """
    Note on paragraph numbers: the brief assumed the source dataset preserves the court's own
    paragraph numbering per chunk. Verified against the dataset's real schema (vaquill/open-india-law,
    config=judgments) — it does not. It chunks each judgment by semantic section_type
    (e.g. "arguments", "facts") with char_start/page_start position locators instead. To still
    give S2 a paragraph number to cite, we best-effort regex-extract court-numbered paragraphs
    (e.g. "12. Learned counsel submits...") from the chunk's original text. This is heuristic,
    not authoritative — chunks with no confidently-detected paragraph marker store an empty list.
    """
    ensure_judgments_collection()

    existing_count = get_judgments_collection_count()
    if existing_count > 0 and not force:
        print(f"[JudgmentSearch] {existing_count} chunks already stored in Qdrant. Skipping ingestion.")
        return

    start_time = time.perf_counter()
    os.makedirs(JUDGMENTS_DATA_PATH, exist_ok=True)

    df, filter_label = _load_filtered_corpus()
    if df is None or df.empty:
        print("[JudgmentSearch] No judgment rows loaded — aborting ingestion.")
        return

    print(f"[JudgmentSearch] Corpus filter used: {filter_label}", flush=True)

    conn = _init_parents_db()
    all_items = []
    seen_hashes = set()
    duplicate_count = 0
    case_count = 0

    for case_id, group in df.groupby("case_id", sort=False):
        group = group.sort_values("chunk_index")
        case_name = str(group["title"].iloc[0]).strip()
        if not case_name:
            case_name = f"{group['petitioner'].iloc[0]} vs {group['respondent'].iloc[0]}".strip()
        court = str(group["court"].iloc[0])
        citation = str(group["citation"].iloc[0]) if pd.notna(group["citation"].iloc[0]) else ""
        disposition = str(group["disposition"].iloc[0]) if pd.notna(group["disposition"].iloc[0]) else ""
        case_date = group["decision_date"].iloc[0]
        case_date_str = case_date.isoformat() if pd.notna(case_date) else ""
        full_text = "\n\n".join(str(t) for t in group["text"].tolist() if pd.notna(t))

        conn.execute(
            "INSERT OR REPLACE INTO judgments "
            "(case_id, case_name, court, date, citation, disposition, full_text, chunk_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (case_id, case_name, court, case_date_str, citation, disposition, full_text, len(group)),
        )
        try:
            from models.database import SessionLocal, Judgment
            _pg = SessionLocal()
            try:
                _pg.merge(Judgment(
                    case_id=str(case_id),
                    case_name=case_name,
                    court=court,
                    date=case_date_str,
                    citation=citation,
                    disposition=disposition,
                    full_text=full_text,
                    chunk_count=len(group)
                ))
                _pg.commit()
            finally:
                _pg.close()
        except Exception as _e:
            pass
        case_count += 1

        for _, row in group.iterrows():
            text = str(row["text"]).strip() if pd.notna(row["text"]) else ""
            if not text:
                continue
            chunk_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            if chunk_hash in seen_hashes:
                duplicate_count += 1
                continue
            seen_hashes.add(chunk_hash)

            paragraph_numbers = _extract_paragraph_numbers(text)

            all_items.append({
                "id": str(uuid.uuid4()),
                "text": text,
                "metadata": {
                    "case_id": str(case_id),
                    "case_name": case_name,
                    "court": court,
                    "date": case_date_str,
                    "year": int(row["year"]) if pd.notna(row["year"]) else None,
                    "citation": citation,
                    "section_type": str(row["section_type"]) if pd.notna(row["section_type"]) else "",
                    "paragraph_numbers": paragraph_numbers,
                    "page_start": int(row["page_start"]) if pd.notna(row["page_start"]) else None,
                    "chunk_index": int(row["chunk_index"]),
                    "total_chunks": int(row["total_chunks"]) if pd.notna(row["total_chunks"]) else None,
                },
            })

    conn.commit()
    conn.close()

    total_chunks = len(all_items)
    print(
        f"[JudgmentSearch] {case_count} judgments, {total_chunks} unique chunks "
        f"({duplicate_count} duplicates skipped).",
        flush=True,
    )

    client = get_qdrant()
    total_stored = 0

    for i in range(0, total_chunks, stream_batch_size):
        batch_items = all_items[i:i + stream_batch_size]
        batch_texts = [item["text"] for item in batch_items]

        batch_num = i // stream_batch_size + 1
        total_batches = (total_chunks + stream_batch_size - 1) // stream_batch_size
        print(f"[JudgmentSearch] Embedding batch {batch_num}/{total_batches} ({len(batch_texts)} chunks)...", flush=True)

        batch_embeddings = get_embeddings(batch_texts, batch_size=32)

        points = [
            PointStruct(
                id=batch_items[j]["id"],
                vector=batch_embeddings[j],
                payload={
                    "text": batch_items[j]["text"],
                    **batch_items[j]["metadata"],
                },
            )
            for j in range(len(batch_items))
        ]

        for attempt in range(3):
            try:
                client.upsert(collection_name=JUDGMENTS_COLLECTION_NAME, points=points)
                total_stored += len(points)
                elapsed = time.perf_counter() - start_time
                rate = total_stored / elapsed if elapsed > 0 else 0
                pct = (total_stored / total_chunks) * 100
                print(
                    f"[JudgmentSearch] Streamed {total_stored}/{total_chunks} chunks ({pct:.1f}%) "
                    f"to Qdrant | Rate: {rate:.1f} chunks/sec | Elapsed: {elapsed:.1f}s",
                    flush=True,
                )
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\n[JudgmentSearch] Failed stream batch at index {i} after 3 attempts: {e}")
                else:
                    print(f"\n[JudgmentSearch] Retry {attempt + 1} for batch index {i}...")
                    time.sleep(2)

    total_time = time.perf_counter() - start_time
    print(
        f"\n[JudgmentSearch] Ingestion completed in {total_time:.2f}s! "
        f"Total chunks in Qdrant: {get_judgments_collection_count()}"
    )


def search_judgments(query: str, top_k: int = 5, court_filter: str = None, case_id_filter: str = None) -> list:
    try:
        ensure_judgments_collection()

        if get_judgments_collection_count() == 0:
            return []

        query_embedding = get_embeddings([query])[0]

        conditions = []
        if court_filter:
            conditions.append(FieldCondition(key="court", match=MatchValue(value=court_filter)))
        if case_id_filter:
            conditions.append(FieldCondition(key="case_id", match=MatchValue(value=case_id_filter)))
        query_filter = Filter(must=conditions) if conditions else None

        try:
            results = get_qdrant().search(
                collection_name=JUDGMENTS_COLLECTION_NAME,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as filter_err:
            print(f"[JudgmentSearch] Filter search failed ({filter_err}), falling back to un-filtered search...")
            results = get_qdrant().search(
                collection_name=JUDGMENTS_COLLECTION_NAME,
                query_vector=query_embedding,
                limit=top_k,
                with_payload=True,
            )

        output = []
        for r in results:
            output.append({
                "text": r.payload.get("text", ""),
                "metadata": {
                    "case_id": r.payload.get("case_id", ""),
                    "case_name": r.payload.get("case_name", ""),
                    "court": r.payload.get("court", ""),
                    "date": r.payload.get("date", ""),
                    "citation": r.payload.get("citation", ""),
                    "section_type": r.payload.get("section_type", ""),
                    "paragraph_numbers": r.payload.get("paragraph_numbers", []),
                    "chunk_index": r.payload.get("chunk_index", 0),
                },
                "score": r.score,
            })

        return output
    except Exception as e:
        print(f"[JudgmentSearch] search_judgments failed: {e}")
        return []


def get_coverage_stats() -> dict:
    """Real counts/date-range backing the S2 coverage banner — computed from PostgreSQL or parents.db."""
    try:
        from models.database import SessionLocal, Judgment
        from sqlalchemy import func
        db = SessionLocal()
        try:
            res = db.query(
                func.count(Judgment.case_id),
                func.min(Judgment.date),
                func.max(Judgment.date)
            ).filter(Judgment.date != "").first()
            if res and res[0] and res[0] > 0:
                count, min_date, max_date = res
                min_year = min_date[:4] if min_date else None
                max_year = max_date[:4] if max_date else None
                return {"case_count": count or 0, "min_year": min_year, "max_year": max_year}
        finally:
            db.close()
    except Exception as e:
        print(f"[JudgmentSearch] PostgreSQL coverage check notice: {e}")

    try:
        conn = sqlite3.connect(_parents_db_path())
        try:
            row = conn.execute(
                "SELECT COUNT(*), MIN(date), MAX(date) FROM judgments WHERE date != ''"
            ).fetchone()
        finally:
            conn.close()
        count, min_date, max_date = row if row else (0, None, None)
        min_year = min_date[:4] if min_date else None
        max_year = max_date[:4] if max_date else None
        return {"case_count": count or 0, "min_year": min_year, "max_year": max_year}
    except Exception as e:
        print(f"[JudgmentSearch] get_coverage_stats error: {e}")
        return {"case_count": 0, "min_year": None, "max_year": None}


def get_coverage_banner() -> str:
    stats = get_coverage_stats()
    if not stats["case_count"]:
        return "Indexed: 0 judgments — corpus not yet ingested."
    year_range = (
        f"{stats['min_year']}–{stats['max_year']}"
        if stats["min_year"] and stats["min_year"] != stats["max_year"]
        else (stats["min_year"] or "")
    )
    return f"Indexed: {stats['case_count']:,} Supreme Court judgments, {year_range}."
