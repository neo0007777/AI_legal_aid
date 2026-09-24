import uuid
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from models.database import Act, Provision, StatuteMapping, IngestionLog
from services.indiacode_client import IndiaCodeClient, IndiaCodeAPIError

logger = logging.getLogger("LexSetu.IndiaCodeIngest")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

TARGET_ACT_QUERIES = [
    {"query": "Bharatiya Nyaya", "target_name": "Bharatiya Nyaya Sanhita"},
    {"query": "Bharatiya Nagarik", "target_name": "Bharatiya Nagarik Suraksha Sanhita"},
    {"query": "Bharatiya Sakshya", "target_name": "Bharatiya Sakshya Adhiniyam"},
    {"query": "Indian Penal Code", "target_name": "Indian Penal Code"},
    {"query": "Code of Criminal Procedure", "target_name": "Code of Criminal Procedure"},
    {"query": "Indian Evidence Act", "target_name": "Indian Evidence Act"},
]

MAPPING_PAIRS = [
    "ipc-bns",
    "crpc-bnss",
    "iea-bsa",
]


class IngestionService:
    """
    Deterministic ingestion service for India Code legal statutes.
    Strictly source-of-truth: no LLMs, no data alteration, no fabricated URLs.
    Handles idempotent upserts, dual SHA-256 hashing, and provenance audit trails.
    """

    def __init__(self, client: Optional[IndiaCodeClient] = None):
        self.client = client or IndiaCodeClient()

    def discover_target_acts(self) -> List[Dict[str, Any]]:
        """
        Discovers exact Act identifiers dynamically from the API search /acts endpoint.
        Never hardcodes Act IDs based on assumptions.
        """
        discovered = []
        for target in TARGET_ACT_QUERIES:
            q = target["query"]
            result = self.client.search_acts(q=q, jurisdiction="CENTRAL", limit=10)
            acts = result.get("acts", [])
            if not acts:
                # Fallback to general query if central filter returns 0
                result = self.client.search_acts(q=q, limit=10)
                acts = result.get("acts", [])

            # Filter for Central jurisdiction primary act matching the query
            selected = None
            for act in acts:
                jurisdiction = (act.get("jurisdiction") or "").upper()
                short_title = act.get("short_title", "")
                if jurisdiction == "CENTRAL":
                    selected = act
                    break
            
            if not selected and acts:
                selected = acts[0]

            if selected:
                discovered.append({
                    "target_name": target["target_name"],
                    "discovered_id": selected["id"],
                    "short_title": selected.get("short_title"),
                    "act_year": selected.get("act_year"),
                    "act_number": selected.get("act_number"),
                    "jurisdiction": selected.get("jurisdiction"),
                    "section_count": selected.get("section_count"),
                })
                logger.info(f"Discovered Act for '{target['target_name']}': ID='{selected['id']}', Title='{selected.get('short_title')}'")
            else:
                logger.warning(f"Could not discover Act for query '{q}' from API.")

        return discovered

    def ingest_act_metadata(self, act_source_id: str, db: Session, run_id: str) -> Act:
        """
        Fetches /acts/{act}, saves raw response and normalized Act metadata idempotently.
        Initializes provision index (numbers and headings) in database.
        """
        res = self.client.get_act(act_source_id)
        data = res["data"]
        raw_text = res["raw_text"]
        raw_hash = res["raw_response_sha256"]
        content_hash = res["content_sha256"]
        act_info = data.get("act", {})

        existing = db.query(Act).filter(Act.source_act_id == act_source_id).first()
        is_update = existing is not None

        if existing:
            act_record = existing
            # Detect whether API data has changed
            if existing.raw_response_sha256 != raw_hash:
                logger.info(f"Act {act_source_id} API payload changed, updating record...")
                act_record.title = act_info.get("short_title") or act_record.title
                act_record.long_title = act_info.get("long_title")
                act_record.year = act_info.get("act_year")
                act_record.act_number = act_info.get("act_number")
                act_record.ministry = act_info.get("ministry")
                act_record.department = act_info.get("department")
                act_record.jurisdiction = act_info.get("jurisdiction")
                act_record.unit = act_info.get("unit") or "section"
                act_record.section_count = act_info.get("section_count")
                act_record.in_force = act_info.get("in_force")
                act_record.spent = act_info.get("spent", False)
                act_record.spent_note = act_info.get("spent_note")
                act_record.source_url = act_info.get("url") or res["source_url"]
                act_record.source_api = res["source_api"]
                act_record.retrieved_at = datetime.utcnow()
                act_record.raw_response_sha256 = raw_hash
                act_record.content_sha256 = content_hash
                act_record.raw_json = raw_text
        else:
            act_record = Act(
                id=str(uuid.uuid4()),
                source_act_id=act_source_id,
                title=act_info.get("short_title") or act_source_id,
                long_title=act_info.get("long_title"),
                year=act_info.get("act_year"),
                act_number=act_info.get("act_number"),
                ministry=act_info.get("ministry"),
                department=act_info.get("department"),
                jurisdiction=act_info.get("jurisdiction"),
                unit=act_info.get("unit") or "section",
                section_count=act_info.get("section_count"),
                in_force=act_info.get("in_force"),
                spent=act_info.get("spent", False),
                spent_note=act_info.get("spent_note"),
                source_url=act_info.get("url") or res["source_url"],
                source_api=res["source_api"],
                source_type="INDIA_CODE_API",
                source_authority="INDIA_CODE_CORPUS",
                retrieved_at=datetime.utcnow(),
                raw_response_sha256=raw_hash,
                content_sha256=content_hash,
                raw_json=raw_text,
            )
            db.add(act_record)

        db.flush()

        # Ingest provision stubs from sections list
        sections = data.get("sections", [])
        provisions_count = 0
        for s in sections:
            # Provision numbers MUST be preserved strictly as strings!
            p_num = str(s.get("number")).strip()
            heading = s.get("heading")
            words = s.get("words")
            url = s.get("url")

            existing_p = db.query(Provision).filter(
                Provision.act_source_id == act_source_id,
                Provision.provision_number == p_num
            ).first()

            if not existing_p:
                p_record = Provision(
                    id=str(uuid.uuid4()),
                    act_id=act_record.id,
                    act_source_id=act_source_id,
                    provision_type=act_record.unit or "section",
                    provision_number=p_num,
                    heading=heading,
                    words=words,
                    source_url=url,
                    source_api=res["source_api"],
                    source_type="INDIA_CODE_API",
                    source_authority="INDIA_CODE_CORPUS",
                    retrieved_at=datetime.utcnow(),
                )
                db.add(p_record)
                provisions_count += 1
            else:
                # Update stub info if heading or words updated
                if heading and not existing_p.heading:
                    existing_p.heading = heading
                if words and not existing_p.words:
                    existing_p.words = words
                if url and not existing_p.source_url:
                    existing_p.source_url = url

        db.commit()

        # Log ingestion
        log = IngestionLog(
            run_id=run_id,
            target=f"act:{act_source_id}",
            status="SUCCESS",
            records_count=len(sections),
            source_url=res["source_url"],
            raw_response_sha256=raw_hash,
            content_sha256=content_hash,
        )
        db.add(log)
        db.commit()

        logger.info(f"Ingested Act {act_source_id}: {len(sections)} provisions indexed.")
        return act_record

    def get_or_fetch_provision(self, act_source_id: str, provision_number: str, db: Session) -> Optional[Provision]:
        """
        Exact provision lookup: Act -> Provision -> Exact verbatim text.
        Queries database first. If verbatim text is not yet stored, fetches from
        /{act}/section/{number}, computes dual hashes, and stores verbatim text idempotently.
        Never alters text, never guesses missing data.
        """
        clean_act = act_source_id.strip().lower()
        clean_num = str(provision_number).strip()

        provision = db.query(Provision).filter(
            Provision.act_source_id == clean_act,
            Provision.provision_number == clean_num
        ).first()

        # If provision exists and has verbatim text, return it immediately from DB
        if provision and provision.raw_text is not None:
            return provision

        # Otherwise fetch exact provision from source API
        try:
            res = self.client.get_section(clean_act, clean_num)
        except IndiaCodeAPIError as e:
            if e.status_code == 404:
                logger.warning(f"Provision {clean_num} of {clean_act} does not exist on source API (404).")
                return None
            raise

        data = res["data"]
        raw_text = res["raw_text"]
        raw_hash = res["raw_response_sha256"]
        content_hash = res["content_sha256"]
        section_obj = data.get("section", {})

        verbatim_text = section_obj.get("text")
        html = section_obj.get("html")
        heading = section_obj.get("heading")
        words = section_obj.get("words")
        canonical_url = data.get("url") or res["source_url"]

        if not provision:
            # Find act record if available
            act = db.query(Act).filter(Act.source_act_id == clean_act).first()
            provision = Provision(
                id=str(uuid.uuid4()),
                act_id=act.id if act else None,
                act_source_id=clean_act,
                provision_type=data.get("unit") or "section",
                provision_number=clean_num,
                heading=heading,
                raw_text=verbatim_text,
                html=html,
                words=words,
                source_url=canonical_url,
                source_api=res["source_api"],
                source_type="INDIA_CODE_API",
                source_authority="INDIA_CODE_CORPUS",
                retrieved_at=datetime.utcnow(),
                raw_response_sha256=raw_hash,
                content_sha256=content_hash,
                raw_json=raw_text,
            )
            db.add(provision)
        else:
            provision.heading = heading or provision.heading
            provision.raw_text = verbatim_text
            provision.html = html or provision.html
            provision.words = words or provision.words
            provision.source_url = canonical_url or provision.source_url
            provision.source_api = res["source_api"]
            provision.retrieved_at = datetime.utcnow()
            provision.raw_response_sha256 = raw_hash
            provision.content_sha256 = content_hash
            provision.raw_json = raw_text

        db.commit()
        db.refresh(provision)
        return provision

    def ingest_mappings_for_pair(self, pair: str, db: Session, run_id: str) -> int:
        """
        Fetches all statutory correspondences for a given transition pair (e.g. ipc-bns).
        Paginates strictly following returned next URLs.
        Stores mappings idempotently as source-listed correspondences, NOT legal conclusions.
        """
        logger.info(f"Ingesting mappings for transition pair: {pair}...")
        mappings = self.client.get_all_mappings(pair=pair)
        count = 0

        for m in mappings:
            from_act = (m.get("from_act") or "").strip().lower()
            from_sec = str(m.get("from_section")).strip() if m.get("from_section") is not None else None
            to_act = (m.get("to_act") or "").strip().lower()
            to_sec = str(m.get("to_section")).strip() if m.get("to_section") is not None else None
            relation = m.get("relation")

            # Check if this exact correspondence exists
            existing = db.query(StatuteMapping).filter(
                StatuteMapping.pair == pair,
                StatuteMapping.from_act == from_act,
                StatuteMapping.from_provision == from_sec,
                StatuteMapping.to_act == to_act,
                StatuteMapping.to_provision == to_sec,
                StatuteMapping.relation == relation
            ).first()

            if not existing:
                mapping_record = StatuteMapping(
                    id=str(uuid.uuid4()),
                    pair=pair,
                    from_act=from_act,
                    from_provision=from_sec,
                    from_heading=m.get("from_heading"),
                    to_act=to_act,
                    to_provision=to_sec,
                    to_heading=m.get("to_heading"),
                    relation=relation,
                    score=m.get("score"),
                    from_url=m.get("from_url"),
                    to_url=m.get("to_url"),
                    source_api=self.client.source_api,
                    source_type="INDIA_CODE_API",
                    source_authority="INDIA_CODE_CORPUS",
                    retrieved_at=datetime.utcnow(),
                    raw_json=m.get("_raw_json"),
                )
                db.add(mapping_record)
                count += 1

        db.commit()

        log = IngestionLog(
            run_id=run_id,
            target=f"mappings:{pair}",
            status="SUCCESS",
            records_count=len(mappings),
            source_url=f"{self.client.base_url}/mappings?pair={pair}",
        )
        db.add(log)
        db.commit()

        logger.info(f"Mappings for pair '{pair}' synced: {len(mappings)} source records ({count} new records added).")
        return len(mappings)

    def run_full_initial_ingestion(self, db: Session) -> Dict[str, Any]:
        """
        Executes complete deterministic initial sync:
        1. Dynamically discovers required Act IDs (BNS, BNSS, BSA, IPC, CrPC, IEA).
        2. Ingests Act metadata and provision tables.
        3. Ingests statutory correspondences for key transitions.
        Idempotent: running multiple times never creates duplicates.
        """
        run_id = f"ingest_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info(f"Starting initial India Code statutory ingestion (Run ID: {run_id})...")

        discovered_acts = self.discover_target_acts()
        acts_ingested = []

        for act in discovered_acts:
            act_id = act["discovered_id"]
            try:
                record = self.ingest_act_metadata(act_id, db, run_id)
                acts_ingested.append({"id": act_id, "title": record.title, "sections": record.section_count})
            except Exception as e:
                logger.error(f"Failed to ingest metadata for Act {act_id}: {e}")
                log = IngestionLog(
                    run_id=run_id,
                    target=f"act:{act_id}",
                    status="FAILED",
                    error_message=str(e),
                )
                db.add(log)
                db.commit()

        mappings_synced = {}
        for pair in MAPPING_PAIRS:
            try:
                total_synced = self.ingest_mappings_for_pair(pair, db, run_id)
                mappings_synced[pair] = total_synced
            except Exception as e:
                logger.error(f"Failed to ingest mappings for pair {pair}: {e}")
                log = IngestionLog(
                    run_id=run_id,
                    target=f"mappings:{pair}",
                    status="FAILED",
                    error_message=str(e),
                )
                db.add(log)
                db.commit()

        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "discovered_acts": acts_ingested,
            "mappings_synced": mappings_synced,
            "timestamp": datetime.utcnow().isoformat(),
        }
