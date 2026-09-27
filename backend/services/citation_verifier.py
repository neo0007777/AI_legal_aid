"""
citation_verifier.py
====================
CRITICAL CITATION-INTEGRITY PIPELINE

Separates:
1. CASE IDENTITY MATCHING
from
2. SUBSTANTIVE PROPOSITION / ENTAILMENT MATCHING

Hard Rule:
A judgment that merely CITES or DISCUSSES an authority is NOT the authority.
Never allow semantic similarity or a related judgment to substitute for the exact cited authority.
IDENTITY FIRST.
ENTAILMENT SECOND.
RELATED CASES THIRD.

10-STAGE ARCHITECTURE:
Stage 1: Citation Identity Resolution (Priority A-F, NO semantic similarity)
Stage 2: Related Case Detection (Classified separately as RELATED_AUTHORITY)
Stage 3: Retrieve the Actual Cited Judgment Only
Stage 4: Proposition Extraction (Verbatim claim preserved)
Stage 5: Evidence Retrieval (From actual cited judgment only, distinguish holding vs submission)
Stage 6: Entailment / NLI (SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, CONTRADICTED)
Stage 7: Case Identity Failure (NOT_FOUND_IN_INDEXED_CORPUS -> external verification -> UNVERIFIED_CITATION / POSSIBLE_FABRICATION)
Stage 8: Related Judgments reported separately
Stage 9: Website Content Filtering (Chrome stripped)
Stage 10: Final Result Model (citation_identity, proposition_verification, source, related_authorities)
"""

import asyncio
import hashlib
import json
import re
import threading
import time
import urllib.parse
from difflib import SequenceMatcher

from services.judgment_search import (
    search_judgments,
    get_coverage_banner,
    resolve_internal_case_identity,
    get_parent_judgment,
)
from services.llm import call_llm, call_groq
from services.citation_parser import (
    parse_citation,
    calculate_name_similarity,
    normalize_case_name,
    normalize_citation_string,
)
from services.external_case_lookup import (
    lookup_and_resolve_external_case,
    ExternalResolutionResult,
    canonicalize_party_name,
)

ENTAILMENT_MODEL = "openai/gpt-oss-120b"
_ENTAILMENT_CONCURRENCY = 3
_entailment_semaphore = threading.Semaphore(_ENTAILMENT_CONCURRENCY)
_RETRY_AFTER_PATTERN = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)

# ── STAGE 4: Citation & Verbatim Proposition Extraction ───────────────────────

CITATION_EXTRACTION_SYSTEM_PROMPT = """You extract case-law citations and their exact claimed legal propositions from Indian legal filings.

For every place the filing cites or relies on a court judgment, extract:
- "case_name": the party names as written in the filing (e.g. "Arnesh Kumar v. State of Bihar"). Copy it VERBATIM from the text — do not correct, expand, or normalize it.
- "citation_string": the reporter/neutral citation if given (e.g. "(2014) 8 SCC 273", "2019 INSC 95"), else "".
- "claimed_content": the EXACT substantive proposition, holding, or quoted text the filing attributes to this case — the actual legal claim being made, in the filing's own words. Do NOT paraphrase or replace it with a generic summary. Keep the exact filing claim.
- "context_snippet": a short verbatim excerpt (under 200 chars) from the filing surrounding the citation, for anchoring.

Rules:
- Only extract citations that ACTUALLY APPEAR in the given text.
- If the same case is cited more than once with different claims, extract each occurrence separately.
- Preserve the exact words used in the filing.

Respond with ONLY a JSON object: {"citations": [{"case_name": "...", "citation_string": "...", "claimed_content": "...", "context_snippet": "..."}]}
If there are no citations, respond {"citations": []}.
"""

_CHUNK_SIZE = 6000
_CHUNK_OVERLAP = 300


def _chunk_text(text: str) -> list:
    if len(text) <= _CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - _CHUNK_OVERLAP
    return chunks


def _parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


def _appears_in_text(case_name: str, text: str) -> bool:
    norm = normalize_case_name(case_name)
    tokens = [t for t in norm.split() if len(t) > 3]
    if not tokens:
        return case_name.lower() in text.lower()
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits >= max(1, len(tokens) // 3)


def extract_citations(filing_text: str) -> tuple:
    """Stage 4 — Extract citations and verbatim claimed propositions from filing text."""
    all_citations = []
    seen = set()
    incomplete = False

    for chunk in _chunk_text(filing_text):
        raw = call_llm(CITATION_EXTRACTION_SYSTEM_PROMPT, chunk, json_mode=True)
        data = _parse_json_object(raw)
        if isinstance(data, list):
            data = {"citations": data}
        if not isinstance(data, dict):
            incomplete = True
            continue
        if "error" in data and "citations" not in data:
            incomplete = True
            continue
        for c in data.get("citations", []):
            if not isinstance(c, dict):
                continue
            case_name = (c.get("case_name") or "").strip()
            if not case_name:
                continue
            if not _appears_in_text(case_name, chunk):
                continue
            key = normalize_case_name(case_name) + "|" + (c.get("citation_string") or "").strip().lower()
            if key in seen:
                continue
            seen.add(key)
            all_citations.append({
                "case_name": case_name,
                "citation_string": (c.get("citation_string") or "").strip(),
                "claimed_content": (c.get("claimed_content") or "").strip(),
                "context_snippet": (c.get("context_snippet") or "").strip(),
            })

    return all_citations, incomplete


# ── STAGE 5 & 6: Entailment (NLI) on the Actual Cited Judgment ────────────────

_TOP_N_EVIDENCE = 5   # Number of semantically ranked paragraphs to pass to NLI
_MIN_PARA_CHARS = 40  # Discard boilerplate (headers, page numbers, etc.)

ENTAILMENT_SYSTEM_PROMPT = """You are an expert legal citation verifier. Your task: decide whether passages from an ACTUAL CITED JUDGMENT support a specific legal proposition claimed in a court filing.

You are given:
1. CLAIM: The exact proposition asserted in the filing.
2. EVIDENCE PASSAGES [P1]…[P5]: The top-5 most semantically relevant paragraphs from the cited judgment, retrieved via embedding similarity. They are listed in descending relevance order.

CRITICAL LEGAL DISTINCTIONS:
- Holding vs. Submission: A lawyer's argument RECORDED in the judgment is NOT the court's holding.
- Holding vs. Quotation: The court quoting another precedent is NOT the court's own holding.
- Holding vs. Obiter: An incidental remark is not a binding principle.

VERDICT OPTIONS:
- "SUPPORTED": The judgment's actual holding directly and clearly supports the claimed proposition.
- "PARTIALLY_SUPPORTED": The judgment supports the general principle but not the full or specific claim.
- "NOT_SUPPORTED": None of the retrieved passages state or support the claimed proposition. Use this honestly — do NOT force-fit a verdict onto an unrelated paragraph.
- "CONTRADICTED": The judgment's holding contradicts or rejects the claimed proposition.

EXTRACTIVE JUSTIFICATION (MANDATORY):
You MUST quote the exact sentence(s) from the evidence that ground your verdict in the field "supporting_quote". Copy verbatim from one of the [P1]-[P5] passages. If no passage contains a grounding sentence, set "supporting_quote" to null and your verdict MUST be "NOT_SUPPORTED".

Respond with ONLY valid JSON:
{
  "verdict": "SUPPORTED" | "PARTIALLY_SUPPORTED" | "NOT_SUPPORTED" | "CONTRADICTED",
  "confidence": "high" | "medium" | "low",
  "holding_type": "holding" | "observation" | "factual_background" | "counsel_submission" | "citation_to_other_authority" | "unclear",
  "supporting_quote": "<verbatim sentence from one of the passages, or null>",
  "evidence_passage_index": <1-5 indicating which passage, or null>,
  "reasoning": "2-3 sentences explaining your verdict, referencing where in the evidence (e.g. 'P2 states...') and noting holding vs submission distinction where relevant."
}
"""


def _semantic_rank_paragraphs(
    paragraphs: list[str], claim: str, top_n: int = _TOP_N_EVIDENCE
) -> list[tuple[float, int, str]]:
    """
    Rank paragraphs against the claim using BGE-small-en cosine similarity.
    Returns list of (score, original_index, paragraph_text) in descending score order.
    Falls back to keyword overlap if the embedding model is unavailable.
    """
    # Filter out very short/boilerplate paragraphs first
    candidates = [(i, p) for i, p in enumerate(paragraphs) if len(p.strip()) >= _MIN_PARA_CHARS]
    if not candidates:
        return []

    try:
        from services.rag import get_embeddings
        texts_to_embed = [claim] + [p for _, p in candidates]
        embeddings = get_embeddings(texts_to_embed)
        claim_vec = embeddings[0]
        para_vecs = embeddings[1:]

        def _cosine(a: list, b: list) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5
            nb = sum(x * x for x in b) ** 0.5
            if na == 0 or nb == 0:
                return 0.0
            return dot / (na * nb)

        scored = [
            (_cosine(claim_vec, para_vecs[j]), candidates[j][0], candidates[j][1])
            for j in range(len(candidates))
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        print(f"[CitationVerifier][Stage5] Semantic ranking: top scores = {[round(s[0], 3) for s in scored[:top_n]]}")
        return scored[:top_n]

    except Exception as emb_err:
        # Graceful fallback: keyword overlap (original logic)
        print(f"[CitationVerifier][Stage5] Embedding unavailable ({emb_err}), falling back to keyword overlap.")
        stop_words = {"and", "the", "be", "to", "in", "of", "a", "is", "for", "that", "this", "it", "as", "by", "with"}
        claim_words = {w for w in re.findall(r"\w+", claim.lower()) if len(w) > 2 and w not in stop_words}
        scored = []
        for orig_i, p in candidates:
            p_words = set(re.findall(r"\w+", p.lower()))
            score = float(len(claim_words & p_words))
            scored.append((score, orig_i, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_n]


def _build_evidence_block(ranked: list[tuple[float, int, str]]) -> str:
    """
    Format the top-N ranked paragraphs into a numbered evidence block for the LLM.
    Each passage is labelled [P1], [P2], … for the LLM to reference in its quote.
    """
    parts = []
    for rank, (score, orig_idx, text) in enumerate(ranked, start=1):
        parts.append(f"[P{rank}] (paragraph {orig_idx + 1}, similarity={score:.3f})\n{text.strip()}")
    return "\n\n".join(parts)


def _extract_evidence_from_paragraphs(
    paragraphs: list[str], claim: str
) -> tuple[str, str, list[tuple[float, int, str]]]:
    """
    Stage 5 — Semantic Evidence Retrieval from the actual cited judgment.

    Uses BGE-small-en embeddings (via the existing RAG infrastructure) to rank every
    paragraph of the judgment against the filing's claim, then returns the top-N
    passages for the NLI model.

    Returns:
        evidence_block  — formatted string with [P1]…[PN] labels for the entailment prompt
        paragraph_label — human-readable label for the best matching paragraph (UI display)
        ranked          — raw ranked list for downstream use
    """
    if not paragraphs:
        return "", None, []

    ranked = _semantic_rank_paragraphs(paragraphs, claim, top_n=_TOP_N_EVIDENCE)
    if not ranked:
        return "", None, []

    evidence_block = _build_evidence_block(ranked)

    # Derive a display label from the best-matching paragraph
    best_score, best_orig_idx, best_p = ranked[0]
    p_num_match = re.search(r"^\s*(\d{1,3})\.\s+", best_p)
    if p_num_match:
        paragraph_label = f"paragraph {p_num_match.group(1)}"
    else:
        paragraph_label = f"passage (section {best_orig_idx + 1})"

    return evidence_block, paragraph_label, ranked


def _run_entailment(claimed_content: str, evidence_block: str) -> dict:
    """Stage 6 — Run NLI against the top-N semantically retrieved passages from the actual cited judgment."""
    user_message = (
        f"CLAIM:\n{claimed_content}\n\n"
        f"EVIDENCE PASSAGES FROM ACTUAL CITED JUDGMENT:\n{evidence_block[:5000]}"
    )
    last_err = None

    with _entailment_semaphore:
        for attempt in range(2):
            try:
                raw = call_groq(ENTAILMENT_SYSTEM_PROMPT, user_message, json_mode=True, model=ENTAILMENT_MODEL)
                data = _parse_json_object(raw)
                if not isinstance(data, dict):
                    raise ValueError(f"Entailment response was not a JSON object: {raw!r}")

                verdict = data.get("verdict", "").upper()
                if verdict not in ("SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED"):
                    if "ENTAILED" in verdict:
                        verdict = "SUPPORTED"
                    elif "CONTRADICT" in verdict:
                        verdict = "CONTRADICTED"
                    else:
                        verdict = "NOT_SUPPORTED"

                # Enforce extractive-justification rule:
                # if LLM claims SUPPORTED/PARTIALLY but gave no quote, downgrade confidence.
                supporting_quote = data.get("supporting_quote") or None
                confidence = data.get("confidence", "medium").lower()
                if confidence not in ("high", "medium", "low"):
                    confidence = "medium"
                if verdict in ("SUPPORTED", "PARTIALLY_SUPPORTED") and not supporting_quote:
                    confidence = "low"  # can't be high/medium without a grounding quote

                if supporting_quote is not None and not isinstance(supporting_quote, str):
                    supporting_quote = str(supporting_quote)
                reasoning = data.get("reasoning", "")
                if not isinstance(reasoning, str):
                    reasoning = str(reasoning)

                return {
                    "verdict": verdict,
                    "confidence": confidence,
                    "holding_type": str(data.get("holding_type", "observation")),
                    "supporting_quote": supporting_quote,
                    "evidence_passage_index": data.get("evidence_passage_index"),
                    "reasoning": reasoning,
                    "technical_failure": False,
                }
            except Exception as e:
                last_err = e
                print(f"[CitationVerifier] Entailment attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    match = _RETRY_AFTER_PATTERN.search(str(e))
                    delay = min(float(match.group(1)), 20.0) + 0.5 if match else 1.5
                    time.sleep(delay)

    return {
        "verdict": "NOT_SUPPORTED",
        "confidence": "low",
        "holding_type": "unclear",
        "supporting_quote": None,
        "evidence_passage_index": None,
        "reasoning": "The verification service was temporarily unavailable and this citation could not be checked. Please retry.",
        "technical_failure": True,
    }


# ── MAIN PER-CITATION VERIFICATION (10 STAGES) ───────────────────────────────

def verify_citation(citation: dict) -> dict:
    """Full 10-stage verification chain for one citation.

    IDENTITY FIRST:
    1. Parse citation details.
    2. Try internal corpus identity resolution (strict priority, NO semantic vector matching).
    3. If internal misses: mark NOT_FOUND_IN_INDEXED_CORPUS, perform external lookup.
    4. Distinguish identity match from related cases (citing judgments -> RELATED_AUTHORITY).
    5. Retrieve actual cited judgment only.

    ENTAILMENT SECOND:
    6. Extract evidence from ACTUAL CITED JUDGMENT only.
    7. Run NLI with holding/submission distinction.

    RELATED CASES THIRD:
    8. Populate related_authorities separately.
    """
    case_name = citation["case_name"]
    citation_string = citation.get("citation_string", "")
    claimed_content = citation.get("claimed_content") or case_name
    context_snippet = citation.get("context_snippet", "")

    parsed = parse_citation(case_name, citation_string, context_snippet)

    # ── CORRECTION MEMORY PRE-CHECK ──
    adjusted_from_correction = False
    correction_meta = None
    try:
        from models.database import SessionLocal
        from services.correction_memory import check_correction
        _db = SessionLocal()
        try:
            corr = check_correction(_db, case_name, citation_string)
            if corr:
                adjusted_from_correction = True
                correction_meta = {
                    "system_output": corr.system_output,
                    "correct_output": corr.correct_output,
                    "direction": corr.direction,
                    "flagged_at": corr.flagged_at.isoformat() if corr.flagged_at else None,
                    "note": corr.note,
                }
        finally:
            _db.close()
    except Exception as e:
        print(f"[CitationVerifier] Correction check notice: {e}")

    # Variables for Stage 10 result model
    identity_status = "NOT_FOUND_IN_INDEXED_CORPUS"
    matched_authority = None
    resolution_method = None
    identity_source = None
    retrieval_source = None
    related_authorities = []
    raw_judgment_text = ""
    judgment_paragraphs = []

    # ── STAGE 1: Internal Identity Resolution ─────────────────────────────────
    internal_case = resolve_internal_case_identity(parsed)
    if internal_case:
        cid = re.sub(r"^ik_", "", str(internal_case.get("case_id", "")))
        if cid.isdigit():
            k_url = f"https://indiankanoon.org/doc/{cid}/"
        else:
            k_url = f"https://indiankanoon.org/search/?formInput={urllib.parse.quote(internal_case.get('case_name') or claimed_name)}"
        matched_authority = {
            "canonical_case_id": internal_case["case_id"],
            "case_name": internal_case["case_name"],
            "citation": internal_case["citation"],
            "court": internal_case["court"],
            "date": internal_case["date"],
            "source_url": k_url,
            "document_hash": hashlib.sha256((internal_case.get("full_text") or "").encode("utf-8")).hexdigest(),
        }
        identity_status = "VERIFIED"
        resolution_method = internal_case.get("resolution_method", "internal_match")
        identity_source = "internal"
        retrieval_source = "internal"
        raw_judgment_text = internal_case.get("full_text") or ""
        judgment_paragraphs = [p.strip() for p in raw_judgment_text.split("\n\n") if p.strip()]

    # ── STAGE 7: External Fallback (if internal missed) ───────────────────────
    if not matched_authority:
        print(f"[CitationVerifier] Citation not in internal index: {case_name!r}. Performing external verification...")
        ext_res: ExternalResolutionResult = lookup_and_resolve_external_case(
            case_name=case_name,
            citation_string=citation_string,
            context=context_snippet,
        )
        related_authorities = ext_res.related_authorities

        if ext_res.identity_matched:
            identity_status = "VERIFIED"
            resolution_method = ext_res.resolution_method
            identity_source = "external"
            retrieval_source = "external"
            matched_authority = {
                "canonical_case_id": ext_res.canonical_case_id,
                "case_name": ext_res.case_name,
                "citation": ext_res.citation,
                "court": ext_res.court,
                "date": ext_res.date,
                "source_url": ext_res.source_url,
                "document_hash": ext_res.document_hash,
            }
            raw_judgment_text = ext_res.clean_text
            judgment_paragraphs = ext_res.paragraphs
        else:
            # Identity failed externally as well
            if ext_res.state == "POSSIBLE_FABRICATION":
                identity_status = "POSSIBLE_FABRICATION"
            elif ext_res.state == "ERROR":
                identity_status = "EXTERNAL_SOURCE_ERROR"
            else:
                identity_status = "UNVERIFIED_CITATION"

    # ── STAGE 5 & 6: Substantive Proposition Verification (ONLY if Identity Verified)
    proposition_status = "NOT_RUN"
    evidence_passage = ""
    paragraph_display = None
    entailment_res = None
    technical_failure = False
    holding_type = "unclear"
    reasoning = ""
    confidence = "low"

    supporting_quote = None
    evidence_passage_index = None

    if identity_status == "VERIFIED" and (raw_judgment_text or judgment_paragraphs):
        # STAGE 5: Semantic Evidence Retrieval — top-N paragraphs via BGE-small embeddings
        evidence_block, paragraph_display, ranked_paras = _extract_evidence_from_paragraphs(
            judgment_paragraphs,
            claimed_content,
        )

        # Fallback: if no paragraphs could be ranked, use raw text prefix
        if not evidence_block and raw_judgment_text:
            evidence_block = f"[P1] (full text fallback)\n{raw_judgment_text[:4000]}"
            evidence_passage = raw_judgment_text[:4000]
        else:
            # Flatten ranked passages for backward-compat display (evidence_passage field)
            evidence_passage = "\n\n".join(p for _, _, p in ranked_paras) if ranked_paras else ""

        # STAGE 6: Entailment / NLI — LLM receives all top-N passages and must quote its source
        entailment_res = _run_entailment(claimed_content, evidence_block)
        proposition_status = entailment_res["verdict"]
        confidence = entailment_res["confidence"]
        holding_type = entailment_res.get("holding_type", "observation")
        reasoning = entailment_res["reasoning"]
        supporting_quote = entailment_res.get("supporting_quote")
        evidence_passage_index = entailment_res.get("evidence_passage_index")
        technical_failure = entailment_res.get("technical_failure", False)

    # ── Overall display status mapping ───────────────────────────────────────
    if identity_status == "VERIFIED":
        if proposition_status == "SUPPORTED":
            display_status = "Verified"
        elif proposition_status == "PARTIALLY_SUPPORTED":
            display_status = "Partial Match"
        else:
            display_status = "Mismatch"
    elif identity_status == "POSSIBLE_FABRICATION":
        display_status = "Possible Fabrication"
    elif identity_status == "UNVERIFIED_CITATION":
        display_status = "Unverified Citation"
    elif identity_status == "EXTERNAL_SOURCE_ERROR":
        display_status = "External Source Error"
    else:
        display_status = "Not Indexed / Not Found"

    if adjusted_from_correction and correction_meta:
        display_status = correction_meta["correct_output"]

    # ── STAGE 10: Assemble Complete Result Model ─────────────────────────────
    source_name = "Indexed corpus (Supreme Court)" if retrieval_source == "internal" else (
        "Indian Kanoon" if retrieval_source == "external" else None
    )
    kanoon_fallback_url = f"https://indiankanoon.org/search/?formInput={urllib.parse.quote((case_name or '') + (' ' + citation_string if citation_string else ''))}"
    final_source_url = (matched_authority.get("source_url") if matched_authority else None) or kanoon_fallback_url

    return {
        # STAGE 10 Core Specification Fields
        "citation_identity": {
            "status": identity_status,
            "matched_case": matched_authority,
            "resolution_method": resolution_method,
            "source": identity_source,
        },
        "proposition_verification": {
            "status": proposition_status,
            "verdict": proposition_status,
            "confidence": confidence,
            "holding_type": holding_type,
            "reasoning": reasoning,
            "supporting_quote": supporting_quote,           # extractive verbatim quote from the judgment
            "evidence_passage_index": evidence_passage_index,  # which [P1]-[P5] passage was cited
            "evidence_passage": evidence_passage,
            "paragraph_display": paragraph_display,
            "technical_failure": technical_failure,
        },
        "source": {
            "retrieval_type": retrieval_source,
            "source_name": source_name,
            "source_url": final_source_url,
            "canonical_case_id": matched_authority["canonical_case_id"] if matched_authority else None,
            "document_hash": matched_authority["document_hash"] if matched_authority else None,
        },
        "related_authorities": related_authorities,

        # Backward compatibility fields for UI, CSV/PDF export, and tests
        "case_name": case_name,
        "citation_string": citation_string,
        "claimed_content": claimed_content,
        "context_snippet": context_snippet,
        "status": display_status,
        "retrieval_source": retrieval_source,
        "matched_case": matched_authority,
        "paragraph_display": paragraph_display,
        "matched_text": evidence_passage[:1200] if evidence_passage else None,
        "adjusted_from_correction": adjusted_from_correction,
        "correction_meta": correction_meta,
        "entailment": {
            "verdict": "entailed" if proposition_status == "SUPPORTED" else (
                "contradicted" if proposition_status == "CONTRADICTED" else "unclear"
            ),
            "confidence": confidence,
            "reasoning": reasoning,
            "technical_failure": technical_failure,
        } if proposition_status != "NOT_RUN" else None,
        "source_link": final_source_url,
        "external_lookup": {
            "state": "FOUND" if retrieval_source == "external" else ("INTERNAL" if retrieval_source == "internal" else "NOT_FOUND"),
            "source": source_name,
            "canonical_title": matched_authority["case_name"] if matched_authority else case_name,
            "doc_url": final_source_url,
        },
    }


# ── Async streaming pipeline ──────────────────────────────────────────────────

async def _verify_one(idx: int, citation: dict) -> tuple:
    result = await asyncio.to_thread(verify_citation, citation)
    return idx, citation, result


async def verify_filing_stream(filing_text: str):
    """Public entrypoint for citation verification streaming."""
    try:
        async for event in _verify_filing_stream_inner(filing_text):
            yield event
    except Exception as e:
        print(f"[CitationVerifier] verify_filing_stream crashed: {e}")
        yield {
            "type": "error",
            "message": "Something went wrong while verifying this filing. Please try again.",
        }


async def _verify_filing_stream_inner(filing_text: str):
    start = time.perf_counter()
    citations, extraction_incomplete = extract_citations(filing_text)
    total = len(citations)

    yield {
        "type": "citations_found",
        "total": total,
        "citations": [{"case_name": c["case_name"], "citation_string": c["citation_string"]} for c in citations],
        "extraction_incomplete": extraction_incomplete,
    }

    if total == 0:
        yield {
            "type": "done",
            "elapsed_seconds": round(time.perf_counter() - start, 2),
            "report": {
                "citations": [],
                "extraction_incomplete": extraction_incomplete,
                "summary": {"verified": 0, "partial_match": 0, "mismatch": 0, "not_found": 0, "external_error": 0, "total": 0},
                "coverage_banner": get_coverage_banner(),
            },
        }
        return

    results = [None] * total
    completed = 0
    tasks = [asyncio.ensure_future(_verify_one(i, c)) for i, c in enumerate(citations)]

    for fut in asyncio.as_completed(tasks):
        idx, citation, result = await fut
        completed += 1
        merged = {**citation, **result}
        results[idx] = merged
        yield {
            "type": "result",
            "completed": completed,
            "total": total,
            "citation_index": idx,
            "citation": merged,
        }

    summary = {
        "total": total,
        "verified": sum(1 for r in results if r["status"] == "Verified"),
        "partial_match": sum(1 for r in results if r["status"] == "Partial Match"),
        "mismatch": sum(1 for r in results if r["status"] == "Mismatch"),
        "possible_fabrication": sum(1 for r in results if r["status"] == "Possible Fabrication"),
        "unverified": sum(1 for r in results if r["status"] in ("Unverified Citation", "Not Indexed / Not Found")),
        "not_found": sum(1 for r in results if r["status"] in ("Not Indexed / Not Found", "Possible Fabrication", "Unverified Citation")),
        "external_error": sum(1 for r in results if r["status"] == "External Source Error"),
        "technical_failures": sum(1 for r in results if (r.get("proposition_verification") or {}).get("technical_failure")),
        "adjusted_from_correction": sum(1 for r in results if r.get("adjusted_from_correction")),
    }

    yield {
        "type": "done",
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "report": {
            "citations": results,
            "extraction_incomplete": extraction_incomplete,
            "summary": summary,
            "coverage_banner": get_coverage_banner(),
        },
    }


# ── Report Rendering (app-wide language switcher + Hinglish) ─────────────────
from services.translate_output import SUPPORTED_LANGUAGES as _TRANSLATE_LANGUAGES, TRANSLATION_DISCLAIMER as TRANSLATION_LABEL

# Reuses the same curated language list as translate_output.py (shared source
# of truth for the app-wide switcher) so Verify-a-Filing responds to every
# language the switcher offers, not just Hindi. Hinglish stays a page-specific
# extra (colloquial Roman-script Hindi), not part of the app-wide list.
_RENDER_LANGUAGE_INSTRUCTIONS = {
    **{code: f"Translate into {desc}." for code, desc in _TRANSLATE_LANGUAGES.items()},
    "hinglish": "Translate into Hinglish -- colloquial Hindi written in the Roman/Latin alphabet, the way Indian speakers commonly write it in chat/text (not Devanagari).",
}


def render_report_in_language(report: dict, language: str) -> dict:
    if language not in _RENDER_LANGUAGE_INSTRUCTIONS:
        raise ValueError(f"Unsupported language: {language!r}. Use one of {list(_RENDER_LANGUAGE_INSTRUCTIONS)}.")

    citations = report.get("citations", [])
    texts = {}
    for i, c in enumerate(citations):
        claim = c.get("claimed_content") or c.get("context_snippet") or ""
        if claim:
            texts[f"{i}_claim"] = claim
        prop_ver = c.get("proposition_verification") or {}
        reasoning = prop_ver.get("reasoning") or (c.get("entailment") or {}).get("reasoning") or ""
        if reasoning:
            texts[f"{i}_reasoning"] = reasoning

    translated = {}
    if texts:
        system_prompt = (
            f"{_RENDER_LANGUAGE_INSTRUCTIONS[language]} You will receive a JSON object mapping "
            "keys to short English legal-filing text snippets. Translate each value. Keep case "
            "names, court names, section numbers, and Act names in their original English/Latin "
            "form (do not transliterate proper nouns or legal citations) -- translate only the "
            "surrounding descriptive language. Respond with ONLY a JSON object using the exact "
            "same keys, each mapped to its translated value."
        )
        try:
            raw = call_llm(system_prompt, json.dumps(texts), json_mode=True)
            clean = raw.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].strip()
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                translated = parsed
        except Exception as e:
            print(f"[CitationVerifier] Translation error: {e}")

    rendered_citations = []
    for i, c in enumerate(citations):
        rendered = dict(c)
        claim_key, reasoning_key = f"{i}_claim", f"{i}_reasoning"
        if claim_key in translated:
            rendered["rendered_claimed_content"] = translated[claim_key]
        if reasoning_key in translated:
            if rendered.get("proposition_verification"):
                rendered["proposition_verification"] = {
                    **rendered["proposition_verification"],
                    "rendered_reasoning": translated[reasoning_key],
                }
            if rendered.get("entailment"):
                rendered["entailment"] = {
                    **rendered["entailment"],
                    "rendered_reasoning": translated[reasoning_key],
                }
        rendered_citations.append(rendered)

    return {
        **report,
        "citations": rendered_citations,
        "rendered_language": language,
        "translation_label": TRANSLATION_LABEL,
    }
