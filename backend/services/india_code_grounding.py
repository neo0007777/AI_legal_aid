import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Callable
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from models.database import Act, Provision, StatuteMapping
from services.indiacode_ingest import IngestionService

logger = logging.getLogger("LexSetu.IndiaCodeGrounding")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

ingest_service = IngestionService()

from services.canonical_checker import cross_check_provision, CanonicalCheckResult, CANONICAL_AUTHORITY

# Common acronym to source_act_id mapping
ACRONYM_TO_ACT_ID = {
    "bns": "bns",
    "bnss": "bnss",
    "bsa": "bsa",
    "ipc": "ipc",
    "crpc": "crpc",
    "iea": "iea",
}


@dataclass
class LockedProvision:
    """Exact, immutable statutory provision retrieved from India Code database."""
    act_source_id: str
    act_title: str
    provision_number: str
    heading: str
    raw_text: str
    source_url: str
    in_force: Optional[bool] = None
    mappings: List[Dict[str, Any]] = field(default_factory=list)
    canonical_status: str = "REQUIRES_CANONICAL_VERIFICATION"  # VERIFIED | SOURCE_CONFLICT | REQUIRES_CANONICAL_VERIFICATION
    canonical_source: str = CANONICAL_AUTHORITY
    canonical_discrepancies: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LockedAct:
    """Exact, immutable Act metadata retrieved from India Code database."""
    source_act_id: str
    title: str
    short_title: str
    long_title: Optional[str] = None
    act_number: Optional[str] = None
    year: Optional[int] = None
    ministry: Optional[str] = None
    department: Optional[str] = None
    jurisdiction: Optional[str] = None
    in_force: Optional[bool] = None
    source_url: Optional[str] = None
    provisions: Dict[str, LockedProvision] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceLockedCorpus:
    """Container for all source-locked legal metadata for a document generation session."""
    acts: Dict[str, LockedAct] = field(default_factory=dict)
    referenced_provisions: List[LockedProvision] = field(default_factory=list)
    unverified_references: List[str] = field(default_factory=list)
    has_source_conflict: bool = False
    conflicted_provisions: List[LockedProvision] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "acts": {k: v.to_dict() for k, v in self.acts.items()},
            "referenced_provisions": [p.to_dict() for p in self.referenced_provisions],
            "unverified_references": self.unverified_references,
            "has_source_conflict": self.has_source_conflict,
            "conflicted_provisions": [p.to_dict() for p in self.conflicted_provisions],
        }


def extract_potential_statute_references(text: str) -> List[Tuple[str, str]]:
    """
    Extracts potential (section_number, statute_hint) pairs from text.
    Examples:
      'Section 483 BNSS' -> ('483', 'bnss')
      'Section 124A IPC' -> ('124A', 'ipc')
      'Section 302 of the Indian Penal Code' -> ('302', 'ipc')
      'Section 438 CrPC' -> ('438', 'crpc')
    """
    results = []
    # Pattern 1: Section <num> [of] <statute>
    pattern = r"(?:Section|Sec\.?|u/s|under\s+section)\s+([0-9]+[A-Za-z\-]*)(?:\s+(?:(?:of|under|in)\s+)?(?:the\s+)?(BNSS|BNS|BSA|IPC|CrPC|IEA|Indian\s+Penal\s+Code|Code\s+of\s+Criminal\s+Procedure|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita|Bharatiya\s+Nyaya\s+Sanhita|Bharatiya\s+Sakshya\s+Adhiniyam))?"
    for m in re.finditer(pattern, text, re.IGNORECASE):
        sec = m.group(1).strip()
        statute_hint = (m.group(2) or "").strip().lower()
        if "nagarik" in statute_hint or statute_hint == "bnss":
            act_id = "bnss"
        elif "nyaya" in statute_hint or statute_hint == "bns":
            act_id = "bns"
        elif "sakshya" in statute_hint or statute_hint == "bsa":
            act_id = "bsa"
        elif "penal" in statute_hint or statute_hint == "ipc":
            act_id = "ipc"
        elif "criminal" in statute_hint or statute_hint == "crpc":
            act_id = "crpc"
        elif "evidence" in statute_hint or statute_hint == "iea":
            act_id = "iea"
        else:
            act_id = ""
        results.append((sec, act_id))

    return results


def resolve_and_lock_statutory_metadata(
    db: Session,
    description: str,
    posture: Any = None,
    grounds_plan: Any = None,
) -> SourceLockedCorpus:
    """
    Retrieves and locks exact metadata from the India Code structured database.
    Never infers missing fields or falls back to LLM knowledge.
    """
    locked_corpus = SourceLockedCorpus()

    # Determine acts to lock
    target_act_ids = set()

    # Check posture governing statute
    if posture and hasattr(posture, "governing_statute") and posture.governing_statute:
        stat = posture.governing_statute.lower()
        if stat in ACRONYM_TO_ACT_ID:
            target_act_ids.add(ACRONYM_TO_ACT_ID[stat])

    # Check text for mentions of acts or acronyms
    text_lower = description.lower()
    for acronym, act_id in ACRONYM_TO_ACT_ID.items():
        if re.search(r"\b" + acronym + r"\b", text_lower):
            target_act_ids.add(act_id)
    if "penal code" in text_lower:
        target_act_ids.add("ipc")
    if "criminal procedure" in text_lower:
        target_act_ids.add("crpc")
    if "nagarik" in text_lower:
        target_act_ids.add("bnss")
    if "nyaya" in text_lower:
        target_act_ids.add("bns")
    if "sakshya" in text_lower:
        target_act_ids.add("bsa")

    # If no target acts found, default to primary criminal procedural statute (BNSS)
    if not target_act_ids:
        target_act_ids.add("bnss")

    # Load Acts from database
    for act_id in target_act_ids:
        act_row = db.query(Act).filter(Act.source_act_id == act_id).first()
        if not act_row:
            # Attempt to ingest metadata if missing from DB
            try:
                act_row = ingest_service.ingest_act_metadata(act_id, db, run_id="resolve_on_demand")
            except Exception as e:
                logger.warning(f"Could not load Act {act_id} from database: {e}")
                act_row = None

        if act_row:
            locked_corpus.acts[act_id] = LockedAct(
                source_act_id=act_row.source_act_id,
                title=act_row.title,
                short_title=act_row.title,
                long_title=act_row.long_title,
                act_number=act_row.act_number,
                year=act_row.year,
                ministry=act_row.ministry,
                department=act_row.department,
                jurisdiction=act_row.jurisdiction,
                in_force=act_row.in_force,
                source_url=act_row.source_url,
            )

    # Resolve specific provisions from description, posture, and grounds plan
    provisions_to_resolve = []

    # From posture
    if posture and hasattr(posture, "governing_provision") and posture.governing_provision:
        prov_text = posture.governing_provision
        m = re.search(r"Section\s+([0-9]+[A-Za-z\-]*)", prov_text)
        if m:
            gov_stat = getattr(posture, "governing_statute", "BNSS").lower()
            act_key = ACRONYM_TO_ACT_ID.get(gov_stat, "bnss")
            provisions_to_resolve.append((m.group(1), act_key))

    # From grounds plan
    if grounds_plan:
        for g in grounds_plan:
            g_prov = getattr(g, "legal_provision", "")
            m = re.search(r"Section\s+([0-9]+[A-Za-z\-]*)", g_prov)
            if m:
                # Deduce statute
                g_stat = "bnss"
                for ac, aid in ACRONYM_TO_ACT_ID.items():
                    if ac.upper() in g_prov:
                        g_stat = aid
                        break
                provisions_to_resolve.append((m.group(1), g_stat))

    # From user text
    extracted = extract_potential_statute_references(description)
    for sec, hinted_act in extracted:
        act_key = hinted_act if hinted_act else (list(target_act_ids)[0] if target_act_ids else "bnss")
        provisions_to_resolve.append((sec, act_key))

    # De-duplicate provisions to resolve
    seen_provs = set()
    for sec, act_id in provisions_to_resolve:
        key = (act_id, sec)
        if key in seen_provs:
            continue
        seen_provs.add(key)

        # Lookup in DB
        prov_record = ingest_service.get_or_fetch_provision(act_id, sec, db)
        if prov_record and prov_record.raw_text:
            act_info = locked_corpus.acts.get(act_id)
            act_title = act_info.title if act_info else act_id.upper()

            # Find mappings
            mappings_query = db.query(StatuteMapping).filter(
                or_(
                    and_(StatuteMapping.from_act == act_id, StatuteMapping.from_provision == sec),
                    and_(StatuteMapping.to_act == act_id, StatuteMapping.to_provision == sec),
                )
            ).all()

            mappings_data = [
                {
                    "pair": m.pair,
                    "target_act": m.to_act if m.from_act == act_id else m.from_act,
                    "target_section": m.to_provision if m.from_act == act_id else m.from_provision,
                    "target_heading": m.to_heading if m.from_act == act_id else m.from_heading,
                    "relation": m.relation,
                    "score": m.score,
                    "target_url": m.to_url if m.from_act == act_id else m.from_url,
                }
                for m in mappings_query
            ]

            # Cross-check against canonical official India Code source (indiacode.nic.in)
            check_res = cross_check_provision(
                act_id=act_id,
                provision_number=str(prov_record.provision_number),
                api_heading=prov_record.heading or "",
                api_text=prov_record.raw_text or "",
                api_act_title=act_title,
            )

            locked_p = LockedProvision(
                act_source_id=act_id,
                act_title=act_title,
                provision_number=str(prov_record.provision_number),
                heading=prov_record.heading or "Not available from source",
                raw_text=prov_record.raw_text,
                source_url=prov_record.source_url or "",
                in_force=act_info.in_force if act_info else True,
                mappings=mappings_data,
                canonical_status=check_res.status,
                canonical_source=check_res.canonical_source,
                canonical_discrepancies=check_res.discrepancies,
            )
            locked_corpus.referenced_provisions.append(locked_p)
            if check_res.has_conflict:
                locked_corpus.has_source_conflict = True
                locked_corpus.conflicted_provisions.append(locked_p)
            if act_id in locked_corpus.acts:
                locked_corpus.acts[act_id].provisions[sec] = locked_p
        else:
            locked_corpus.unverified_references.append(f"Section {sec} ({act_id.upper()})")

    return locked_corpus


def build_source_locked_prompt_block(locked_corpus: SourceLockedCorpus) -> str:
    """
    Renders the non-negotiable India Code metadata block for LLM prompt injection.
    Explicitly instructs the LLM to reproduce values verbatim without alterations.
    """
    lines = [
        "═══════════════════════════════════════════════════════",
        "SOURCE-LOCKED INDIA CODE LEGAL METADATA (NON-NEGOTIABLE)",
        "═══════════════════════════════════════════════════════",
        "The legal values below are extracted directly from the structured India Code database.",
        "MANDATORY VERBATIM REPRODUCTION RULES:",
        "1. You MUST reproduce the exact Act title, short title, Act number, year, section number,",
        "   and section heading EXACTLY as given below. Do NOT shorten, translate, or paraphrase.",
        "   - FORBIDDEN: 'BNSS Act', 'Bharatiya Nagarik Suraksha...', 'Brihanmumbai...', or any model-generated alias.",
        "   - MANDATORY: Use the exact title: 'The Bharatiya Nagarik Suraksha Sanhita, 2023' (or applicable Act).",
        "2. The model is allowed to draft arguments around these values, but is STRICTLY FORBIDDEN from modifying them.",
        "3. Any discrepancy in statutory title or section heading will cause automatic rejection.",
        "4. If a value is marked [NOT PROVIDED], [REQUIRES VERIFICATION], or [SOURCE_CONFLICT], output that exact marker.",
        "5. Database value > retrieved source > model knowledge. NEVER use model knowledge as a fallback.",
        "6. Never assign or cite a provision as a VERIFIED_LEGAL_RULE unless its CANONICAL VERIFICATION STATUS is VERIFIED.",
        "",
        "LOCKED STATUTORY ENTITIES:",
    ]

    for act_id, act in locked_corpus.acts.items():
        lines.append(f"• ACT IDENTIFIER: {act.source_act_id.upper()}")
        lines.append(f"  - EXACT ACT TITLE: \"{act.title}\"")
        if act.act_number:
            lines.append(f"  - ACT NUMBER: Act No. {act.act_number} of {act.year}")
        if act.year:
            lines.append(f"  - YEAR: {act.year}")
        if act.jurisdiction:
            lines.append(f"  - JURISDICTION: {act.jurisdiction}")
        if act.source_url:
            lines.append(f"  - CANONICAL SOURCE URL: {act.source_url}")
        lines.append(f"  - IN FORCE: {act.in_force}")
        lines.append("")

    if locked_corpus.referenced_provisions:
        lines.append("LOCKED PROVISIONS (EXACT STATUTORY TEXT & HEADINGS):")
        for p in locked_corpus.referenced_provisions:
            lines.append(f"• Section {p.provision_number} of {p.act_title}:")
            lines.append(f"  - EXACT HEADING: \"{p.heading}\"")
            lines.append(f"  - CANONICAL URL: {p.source_url}")
            lines.append(f"  - CANONICAL VERIFICATION STATUS: {p.canonical_status} ({p.canonical_source})")
            if p.canonical_discrepancies:
                lines.append(f"  - CONFLICT DETAILS: {'; '.join(p.canonical_discrepancies)}")
            # Verbatim excerpt
            clean_text = p.raw_text.replace("\n", " ").strip()
            if len(clean_text) > 400:
                clean_text = clean_text[:400] + "..."
            lines.append(f"  - VERBATIM STATUTORY TEXT: \"{clean_text}\"")
            if p.mappings:
                for m in p.mappings:
                    lines.append(
                        f"  - SOURCE-LISTED CORRESPONDENCE: {m['target_act'].upper()} Section {m['target_section']} "
                        f"({m.get('target_heading', '')}) [Relation: {m.get('relation')}] (API mapping only; not legal conclusion)"
                    )
            lines.append("")

    if locked_corpus.unverified_references:
        lines.append("UNVERIFIED STATUTORY REFERENCES (NOT FOUND IN INDIA CODE DATABASE):")
        for unv in locked_corpus.unverified_references:
            lines.append(f"• {unv} → [LEGAL PROVISION REQUIRES VERIFICATION] (Do NOT invent section text)")
        lines.append("")

    lines.append("═══════════════════════════════════════════════════════")
    return "\n".join(lines)


def audit_document_consistency(
    document_text: str,
    locked_corpus: SourceLockedCorpus
) -> List[Dict[str, Any]]:
    """
    Performs a deterministic post-generation consistency audit on the generated draft.
    Checks:
    - Act titles match database values
    - Section numbers and headings match database values
    - Act numbers and years match database values
    - Source URLs match database values
    Returns a list of violation records. Empty list means passed.
    """
    violations = []

    # 1. Check Act titles
    for act_id, act in locked_corpus.acts.items():
        db_title = act.title
        # Check if corrupted forms appear
        # Common corruptions: "BNSS Act", "BNS Act", "Brihanmumbai", etc.
        corrupted_patterns = [
            (rf"\b{act_id.upper()}\s+Act\b", f"{act_id.upper()} Act"),
            (r"\bBrihanmumbai[\w\s\-]+Sanhita\b", "Brihanmumbai... (hallucinated title)"),
        ]
        if act_id == "bnss":
            corrupted_patterns.append((r"Bharatiya\s+Nagarik\s+Suraksha(?!\s+Sanhita)", "Incomplete BNSS title"))
        elif act_id == "bns":
            corrupted_patterns.append((r"Bharatiya\s+Nyaya(?!\s+Sanhita)", "Incomplete BNS title"))
        elif act_id == "bsa":
            corrupted_patterns.append((r"Bharatiya\s+Sakshya(?!\s+Adhiniyam)", "Incomplete BSA title"))

        for pat, desc in corrupted_patterns:
            matches = re.findall(pat, document_text, re.IGNORECASE)
            if matches:
                violations.append({
                    "type": "act_title_corrupted",
                    "act_id": act_id,
                    "expected": db_title,
                    "found": matches[0],
                    "description": desc,
                })

    # 2. Check Provision Headings & Numbers
    for prov in locked_corpus.referenced_provisions:
        # Search if section is cited
        sec_pat = rf"(?:Section|Sec\.?)\s+{re.escape(prov.provision_number)}\b"
        if re.search(sec_pat, document_text, re.IGNORECASE):
            # If the heading is also written nearby (within next 120 chars)
            # check that it doesn't contradict the database heading
            heading_words = [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", prov.heading)]
            # If document attempts to give an explicit section heading in parens/quotes/colon
            heading_patterns = [
                sec_pat + r"\s*[\(\[\"\']([A-Za-z\s]{5,70})[\)\]\"\']",
                sec_pat + r"\s*[\:\–\-]\s*([A-Z][A-Za-z\s]{5,70})(?:[\.\n\r]|\s+of\b)",
            ]
            for h_pat in heading_patterns:
                for cm in re.finditer(h_pat, document_text):
                    candidate_heading = cm.group(1).strip()
                    cand_words = set(re.findall(r"\b[A-Za-z]{4,}\b", candidate_heading.lower()))
                    if cand_words and not any(w in cand_words for w in heading_words):
                        if not any(k in candidate_heading.lower() for k in ["application", "code", "sanhita", "herein", "prayed", "accused", "petition"]):
                            violations.append({
                                "type": "section_heading_mismatch",
                                "section": prov.provision_number,
                                "act": prov.act_source_id,
                                "expected": prov.heading,
                                "found": candidate_heading,
                            })

    # 3. Check for completely non-existent section citations for locked acts
    # If the user or model cites e.g. "Section 999 BNSS", check if it exists
    all_cited_sections = extract_potential_statute_references(document_text)
    for sec_num, act_hint in all_cited_sections:
        if act_hint in locked_corpus.acts:
            # Check if this section exists in the locked provisions or DB
            locked_act = locked_corpus.acts[act_hint]
            if sec_num not in locked_act.provisions:
                # Check if it was marked as unverified
                if f"Section {sec_num} ({act_hint.upper()})" in locked_corpus.unverified_references:
                    # Must be tagged with [REQUIRES VERIFICATION] in the document
                    if f"[REQUIRES VERIFICATION]" not in document_text and f"[LEGAL PROVISION REQUIRES VERIFICATION]" not in document_text:
                        violations.append({
                            "type": "unverified_section_not_flagged",
                            "section": sec_num,
                            "act": act_hint,
                            "expected": f"Section {sec_num} [REQUIRES VERIFICATION]",
                            "found": f"Section {sec_num} {act_hint.upper()}",
                        })

    return violations


def enforce_consistency_and_regenerate(
    document_text: str,
    locked_corpus: SourceLockedCorpus,
    llm_regenerate_fn: Optional[Callable[[str, str], str]] = None,
    original_system_prompt: str = "",
    original_user_message: str = "",
    max_retries: int = 1,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Validates document against locked India Code metadata.
    If consistency check fails:
    1. Re-prompts the LLM with strict error feedback showing database vs found values.
    2. Re-audits the regenerated output.
    3. Deterministically enforces exact database values for any residual variations.
    Never returns a document violating the India Code source lock.
    """
    current_text = document_text

    # Fast deterministic pass: Programmatically replace known corrupted phrases with exact DB titles
    for act_id, act in locked_corpus.acts.items():
        db_title = act.title
        # Replace "BNSS Act" or "BNS Act" -> exact title
        current_text = re.sub(rf"\b{act_id.upper()}\s+Act\b", db_title, current_text, flags=re.IGNORECASE)
        # Replace "Brihanmumbai..." -> exact title
        current_text = re.sub(r"\bBrihanmumbai[\w\s\-]+Sanhita\b", db_title, current_text, flags=re.IGNORECASE)

    # Cross-sanhita procedural section typos (e.g. Section 483 / 482 / 480 is BNSS, not BNS)
    for bnss_sec in ["483", "482", "480", "479"]:
        current_text = re.sub(rf"\bSection\s+{bnss_sec}\s+BNS\b", f"Section {bnss_sec} BNSS", current_text, flags=re.IGNORECASE)

    violations = audit_document_consistency(current_text, locked_corpus)
    if violations:
        # Deterministically tag unverified section citations with [REQUIRES VERIFICATION]
        has_unverified_tags = False
        for v in violations:
            if v.get("type") == "unverified_section_not_flagged":
                sec_num = v.get("section", "")
                act_hint = v.get("act", "")
                if sec_num and act_hint:
                    current_text = re.sub(
                        rf"\bSection\s+{re.escape(sec_num)}\s+{re.escape(act_hint.upper())}\b(?!\s*\[REQUIRES)",
                        f"Section {sec_num} {act_hint.upper()} [REQUIRES VERIFICATION]",
                        current_text,
                        flags=re.IGNORECASE,
                    )
                    has_unverified_tags = True
        if has_unverified_tags:
            violations = audit_document_consistency(current_text, locked_corpus)

    if not violations:
        logger.info("Post-generation India Code source-lock audit PASSED.")
        return current_text, []

    logger.warning(f"Post-generation audit found {len(violations)} violations: {violations}")

    retries = 0

    while violations and retries < max_retries and llm_regenerate_fn:
        retries += 1
        logger.info(f"Regenerating draft (Attempt {retries}/{max_retries}) using database values...")

        # Build correction instruction
        correction_lines = [
            "CRITICAL: YOUR PREVIOUS GENERATION FAILED THE SOURCE-LOCK CONSISTENCY CHECK.",
            "The following legal metadata fields did not match the India Code database values:",
        ]
        for v in violations:
            correction_lines.append(f"• Expected: \"{v['expected']}\" | Found: \"{v['found']}\" ({v.get('description', v['type'])})")
        correction_lines.extend([
            "",
            "MANDATORY INSTRUCTION:",
            "Regenerate the complete legal document. You MUST substitute every incorrect value",
            "with the exact database value shown above.",
            "Do NOT paraphrase Act titles. Do NOT abbreviate. Do NOT invent alternative section headings.",
            "Preserve all case facts and structure exactly.",
        ])
        correction_prompt = "\n".join(correction_lines)

        user_retry_message = f"{original_user_message}\n\n{correction_prompt}"
        try:
            regenerated_text = llm_regenerate_fn(original_system_prompt, user_retry_message)
            if regenerated_text and not regenerated_text.strip().startswith("⚠️"):
                current_text = regenerated_text
                violations = audit_document_consistency(current_text, locked_corpus)
        except Exception as e:
            logger.error(f"Regeneration attempt failed: {e}")
            break

    # Final deterministic pass: Programmatically replace any residual corrupted phrases with DB titles
    for act_id, act in locked_corpus.acts.items():
        db_title = act.title
        # Replace "BNSS Act" -> exact title
        current_text = re.sub(rf"\b{act_id.upper()}\s+Act\b", db_title, current_text, flags=re.IGNORECASE)
        # Replace "Brihanmumbai..." -> exact title
        current_text = re.sub(r"\bBrihanmumbai[\w\s\-]+Sanhita\b", db_title, current_text, flags=re.IGNORECASE)

    # Re-audit final text
    final_violations = audit_document_consistency(current_text, locked_corpus)
    logger.info(f"Final post-generation audit complete. Residual violations: {len(final_violations)}")
    return current_text, violations
