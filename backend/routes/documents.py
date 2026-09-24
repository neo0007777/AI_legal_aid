from fastapi import APIRouter, HTTPException, Depends, Request
import logging
from sqlalchemy.orm import Session
from models.database import get_db, User, QueryLog
from models.schemas import (
    DraftRequest, DraftResponse,
    ContradictionRequest, ContradictionResponse, ContradictionPoint,
    SearchSource
)
from services.rag import search_drafts
from services.llm import call_llm
from services.contradiction import find_contradictions
from services.review_engine import run_two_pass_refinement
from services.fact_manifest import build_manifest
from services.statute_map import validate_sections_in_text
from services.legal_reasoning_engine import (
    identify_procedural_posture,
    build_ground_traceability_plan,
    render_legal_reasoning_prompt_block,
)
from services.india_code_grounding import (
    resolve_and_lock_statutory_metadata,
    build_source_locked_prompt_block,
    enforce_consistency_and_regenerate,
)
from utils.auth import get_current_user
from utils.encryption import encrypt

router = APIRouter()
logger = logging.getLogger("LexSetu.Documents")


# ═══════════════════════════════════════════════════════
# SYSTEM PROMPT — Part A: Role & Constraints
# ═══════════════════════════════════════════════════════
# Kept intentionally SHORT so the LLM actually follows it.
# The fact manifest (Part B) is injected dynamically per request.

DRAFT_SYSTEM_PROMPT = """You are a legal drafting agent focused on GROUNDEDNESS and ACCURACY.

Your highest priority is NOT to make the document look complete.
Your highest priority is to ensure that every factual and legal assertion is supported.

Follow these rules for every case, regardless of offence, statute, court, jurisdiction, or type of application.

1. FACT GROUNDING

For every factual statement in the generated document, determine its source before writing it.

A fact may come only from:
- explicit user input
- uploaded case documents
- verified external legal/source material

If a fact is not available from these sources:
- do not infer it
- do not guess it
- do not convert absence of information into a negative fact
- mark it as [NOT PROVIDED] or [REQUIRES VERIFICATION]
- or omit it if it is not necessary

Never invent:
- arrest date
- custody status
- custody duration
- FIR date
- police station
- district
- chargesheet status
- investigation status
- trial stage
- criminal antecedents
- residence
- employment
- family circumstances
- medical circumstances
- evidence
- witness status
- recovery
- previous bail history
- co-accused status
- defence facts

2. NEVER CONFUSE ABSENCE OF DATA WITH ABSENCE OF A FACT

These are NOT equivalent:
"No information was provided about witness intimidation."
and
"There is no possibility of witness intimidation."

The first is grounded.
The second is an unsupported factual conclusion.
Always use the grounded version.

3. SEPARATE FACTS FROM LEGAL ARGUMENTS

Internally classify every generated statement as one of:
USER_FACT
DOCUMENT_FACT
VERIFIED_LEGAL_RULE
GENERATED_LEGAL_ARGUMENT
UNKNOWN
REQUIRES_VERIFICATION

Only USER_FACT and DOCUMENT_FACT may be presented as facts about the case.
GENERATED_LEGAL_ARGUMENT may be used as advocacy/drafting language, but must never contain invented factual premises.
UNKNOWN and REQUIRES_VERIFICATION must never be silently converted into factual assertions.

4. LEGAL PROVISION & PROCEDURAL POSTURE VALIDATION

Do NOT generate legal grounds by matching generic keywords such as "bail" to section numbers.
First identify the exact application type and procedural posture, then determine the governing
statute and provision from authoritative legal sources.
- Distinguish regular bail from anticipatory bail and do NOT use provisions governing one type
  of relief for another (e.g. never cite Section 482 BNSS / 438 CrPC in regular bail; never
  cite Section 483 BNSS / 439 CrPC in anticipatory bail).
- Every legal proposition must be independently verified against the actual statutory text
  or an authoritative judgment. A section number appearing in a statute is not evidence that
  the section supports the proposition being generated. Verify:
  PROVISION → STATUTORY TEXT → PROPOSITION.
- If the user provides only a section number, preserve exactly what the user provided and flag
  the statute for verification: Section [number] [STATUTE REQUIRES VERIFICATION].
- Do not silently convert an old statutory provision into a new statutory provision.
- If the legal provision cannot be verified, mark it [LEGAL PROVISION REQUIRES VERIFICATION].

5. PROCEDURAL STATUS

Do not infer the procedural stage from the requested document type.
For example, the fact that the user asks for a bail application does NOT prove:
- the accused is in judicial custody
- the accused has been arrested
- investigation is complete
- chargesheet has been filed
- trial has commenced
- charges have been framed
Only state these when supported by the FACT MANIFEST.

6. CASE LAW / CITATION INTEGRITY & PROPOSITION VERIFICATION

Citation verification must happen at the proposition level.
Never generate a citation merely because it looks plausible.
For every authority, verify:
CASE NAME ↕ CITATION ↕ ACTUAL JUDGMENT ↕ PROPOSITION ATTRIBUTED TO IT

A citation is valid ONLY if the judgment exists, the case/citation matches, and the judgment
actually supports the proposition attributed to it.
- If the case cannot be verified: [CITATION REQUIRES VERIFICATION]
- If a real judgment exists but does not support the proposition: [PROPOSITION MISMATCH]
- Do not fabricate SCC citations, URLs, court names, dates, paragraph numbers, or quotations.

7. DO NOT OVERSTATE LEGAL PRINCIPLES

Avoid converting broad judicial principles into absolute statutory rules.
Do not write formulations such as:
"the statute guarantees..."
"the accused is entitled as a matter of right..."
"the court must..."
"the law conclusively provides..."
unless the exact proposition has been verified from statutory text.
Use precise, qualified language where appropriate.

8. ARGUMENT TYPOLOGY & CASE-SPECIFIC GROUNDS

Do not generate a legal argument merely because it is common in bail applications.
For every argument, determine whether it is:
(1) VERIFIED_LEGAL_RULE (statutory text or binding statutory rule)
(2) GENERAL_JUDICIAL_PRINCIPLE (e.g. Article 21, presumption of innocence, proportionality)
(3) CASE_SPECIFIC_FACTUAL_APPLICATION (e.g. flight risk, tampering, antecedents, custody duration)

CRITICAL RULE:
Only Category 3 requires supporting case facts, and Category 3 MUST NOT be generated
when those facts are absent! If such a ground is relevant but cannot yet be established, write:
"[CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS]"

RULE ON UNKNOWN FACTS:
Never convert an unknown fact into a negative assertion. [NOT PROVIDED] means unknown, NOT "no".
- If criminal antecedents are not supplied: do NOT say the accused has no convictions or clean record.
- If evidence has not been reviewed: do NOT say there is no evidence of tampering or no possibility of tampering.
- If custody duration is unknown: do NOT make a prolonged-detention argument.

9. DO NOT USE GENERIC BOILERPLATE AS FACT

Generic legal language is allowed.
However, the following distinction must always be maintained:
BAD:
"The petitioner has strong family ties and therefore will not abscond."
GOOD:
"The applicant may rely on residential/family ties as a factor relevant to flight risk, subject to supporting facts being provided."

10. INTERNAL GROUND METADATA & SOURCE TRACEABILITY

For every generated legal ground, internally store and maintain:
GROUND: Name/title of ground
LEGAL_PROVISION: Section and Act verified from statutory text
SOURCE: Explicit source of authority
EXACT_PROPOSITION_SUPPORTED: Precise proposition supported by text
CASE_FACTS_REQUIRED: Specific facts required for Category 3
CASE_FACTS_AVAILABLE: Facts present in manifest
VERIFICATION_STATUS: VERIFIED | LEGAL_PROVISION_REQUIRES_VERIFICATION | CASE_FACTS_MISSING | PROPOSITION_MISMATCH

11. INPUT QUALITY ANALYSIS

Before drafting, first determine:
A. What is known?
B. What is unknown?
C. What is legally uncertain?
D. What requires verification?
E. Which arguments can safely be generated from the available information?
Do not hide this uncertainty merely because the final output should look professional.

12. OUTPUT DESIGN

Generate the legal document in this structure:
- Heading / Cause Title
- Verified Case Information
- Factual Background
- Legal Grounds
- Prayer
- Verification / Required Completion Fields

Where information is missing, use [NOT PROVIDED] or [REQUIRES VERIFICATION].
Do NOT fabricate content to make paragraphs sound complete.

13. FINAL SELF-CHECK

Before returning the document, perform a grounding audit.
For every factual sentence ask:
"Where did this fact come from?"
If there is no source: DELETE IT or MARK IT [REQUIRES VERIFICATION].

For every legal proposition ask:
"What authority supports this?"
If unverified: MARK IT [CITATION REQUIRES VERIFICATION].

For every conclusion ask:
"Is this conclusion based on actual case facts?"
If not: rewrite it as a conditional/legal argument or remove it.

The final document should prefer being incomplete but accurate over being complete but invented.

CORE PRINCIPLE:
NEVER FILL A KNOWLEDGE GAP WITH A PLAUSIBLE-SOUNDING LEGAL FACT.
Groundedness is more important than completeness.
Verification is more important than fluency.
Accuracy is more important than making the document look court-ready."""


def _build_statute_validation_block(description: str) -> str:
    """Validate statutory references in user input and produce a guidance block enforcing Rule 4."""
    refs = validate_sections_in_text(description)
    if not refs:
        return ""

    lines = [
        "",
        "═══════════════════════════════════════════════════════",
        "STATUTE VALIDATION RESULTS (RULE 4 COMPLIANCE)",
        "═══════════════════════════════════════════════════════",
    ]
    for ref in refs:
        status_icon = {"verified": "✓", "mapped": "⟶", "unverified": "⚠", "ambiguous": "?"}.get(ref.status, "?")
        lines.append(f"  {status_icon} {ref.original_input} → Section {ref.section} {ref.statute} [{ref.status}]")
        if ref.note:
            lines.append(f"    Note: {ref.note}")
    lines.append("")
    lines.append("LEGAL PROVISION VALIDATION RULES:")
    lines.append("• Preserve exactly what the user provided. Do NOT silently convert old statutory provisions into new statutory provisions.")
    lines.append("• If only a section number is provided without a statute, preserve Section [number] and flag statute as [STATUTE REQUIRES VERIFICATION].")
    lines.append("• Never infer statute name, corresponding provision, amendment, repeal, or transition rule unless verified.")
    lines.append("═══════════════════════════════════════════════════════")
    return "\n".join(lines)


def _build_provenance_report(manifest) -> dict:
    """Build a provenance report summarizing what was provided, missing, and generated."""
    provided = [
        {"field": f.label, "value": f.value, "source": f.source}
        for f in manifest.provided_facts
    ]
    missing_material = [
        {"field": f.label, "material": True}
        for f in manifest.missing_facts if f.material
    ]
    missing_optional = [
        {"field": f.label, "material": False}
        for f in manifest.missing_facts if not f.material
    ]
    return {
        "provided_facts": provided,
        "missing_material": missing_material,
        "missing_optional": missing_optional,
        "total_provided": len(provided),
        "total_missing_material": len(missing_material),
        "total_missing_optional": len(missing_optional),
    }


@router.post("/draft", response_model=DraftResponse)
def generate_draft(
    req: DraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    local_only = request.headers.get("x-local-only", "").lower() == "true"
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    try:
        # ── Step 1: Build Fact Manifest ──────────────────────
        manifest = build_manifest(
            description=req.description,
            category=req.category,
            template_id=req.template_id,
            structured_input=req.structured_input,
        )
        fact_manifest_block = manifest.to_prompt_block()

        # ── Step 2: Identify Procedural Posture & Build Legal Grounding Plan ──
        posture = identify_procedural_posture(
            description=req.description,
            structured_input=req.structured_input,
            manifest=manifest,
        )
        grounds_plan = build_ground_traceability_plan(posture, manifest)
        legal_reasoning_block = render_legal_reasoning_prompt_block(posture, grounds_plan)

        # ── Step 3: Retrieve & Lock India Code Metadata ──────
        locked_corpus = resolve_and_lock_statutory_metadata(
            db=db,
            description=req.description,
            posture=posture,
            grounds_plan=grounds_plan,
        )

        # ── Step 3.5: Halt Generation if SOURCE_CONFLICT is detected ──────
        # Mandatory rule: If the API and canonical source disagree, mark the record
        # SOURCE_CONFLICT and do not generate a legal document from it until resolved.
        conflicts = []
        if locked_corpus.has_source_conflict:
            for cp in locked_corpus.conflicted_provisions:
                disc_str = "; ".join(cp.canonical_discrepancies) if cp.canonical_discrepancies else "Discrepancy with canonical official source"
                conflicts.append(f"Section {cp.provision_number} ({cp.act_title}): {disc_str}")
        for g in grounds_plan:
            if g.verification_status == "SOURCE_CONFLICT" or g.ground_category == "SOURCE_CONFLICT":
                if g.ground_text not in conflicts:
                    conflicts.append(g.ground_text)

        if conflicts:
            conflict_msg = " | ".join(conflicts)
            logger.error(f"Document generation blocked due to SOURCE_CONFLICT: {conflict_msg}")
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Document generation blocked: Statutory provision is marked SOURCE_CONFLICT between the API "
                    f"and canonical official India Code source (indiacode.nic.in). {conflict_msg}. "
                    "Do not generate a legal document from it until resolved."
                ),
            )

        source_lock_block = build_source_locked_prompt_block(locked_corpus)
        statute_block = _build_statute_validation_block(req.description)

        # ── Step 4: Retrieve templates from Qdrant ───────────
        results = []
        if req.category:
            results = search_drafts(req.description, n_results=req.n_results, category_filter=req.category)
        if not results:
            results = search_drafts(req.description, n_results=req.n_results)

        if not results:
            raise HTTPException(
                status_code=404,
                detail="No templates found. Make sure you have run ingest.py first."
            )

        context = "\n\n---\n\n".join([
            f"Template: {r['metadata']['filename']}\nCategory: {r['metadata']['category']}\n\n{r['text']}"
            for r in results
        ])

        # ── Step 5: Compose the full prompt ──────────────────
        full_system_prompt = (
            DRAFT_SYSTEM_PROMPT
            + "\n\n" + fact_manifest_block
            + "\n\n" + legal_reasoning_block
            + "\n\n" + source_lock_block
        )
        if statute_block:
            full_system_prompt += "\n" + statute_block

        user_message = f"""Draft Request: {req.description}
{f"Document Category: {req.category}" if req.category else ""}

Structure the document strictly following Rule 12 (Output Design):
1. Heading / Cause Title
2. Verified Case Information
3. Factual Background (state ONLY verified facts; use [NOT PROVIDED] for unknown facts)
4. Legal Grounds (qualify unverified grounds; use [CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS] where factual basis is absent)
5. Prayer
6. Verification / Required Completion Fields

Reference Templates from Database:
{context}"""

        # ── Step 6: Generate draft with higher token budget ──
        initial_draft = call_llm(
            full_system_prompt, user_message,
            force_local=local_only,
            max_tokens=4096,
        )

        if not initial_draft or initial_draft.strip().startswith("⚠️ AI service temporarily unavailable"):
            detail = (
                "Local Ollama is unavailable (local-only mode is on, so Groq was not used). "
                "Make sure Ollama is running locally."
                if local_only else
                "AI service temporarily unavailable. Please verify your Groq API key and network connection."
            )
            raise HTTPException(status_code=503, detail=detail)

        # ── Step 7: Post-Generation Consistency Check & Source-Lock Enforcement ──
        def regenerate_callback(sys_p: str, usr_m: str) -> str:
            return call_llm(sys_p, usr_m, force_local=local_only, max_tokens=4096)

        final_draft, audit_violations = enforce_consistency_and_regenerate(
            document_text=initial_draft,
            locked_corpus=locked_corpus,
            llm_regenerate_fn=regenerate_callback,
            original_system_prompt=full_system_prompt,
            original_user_message=user_message,
            max_retries=1,
        )
        review_report = None

        # ── Step 8: Build provenance report ──────────────────
        provenance = _build_provenance_report(manifest)
        provenance["source_locked_corpus"] = locked_corpus.to_dict()
        provenance["source_lock_violations_detected"] = len(audit_violations)

        try:
            db.add(QueryLog(
                user_id=current_user.id,
                query_type="draft",
                encrypted_query=encrypt(req.description),
            ))
            db.commit()
        except Exception:
            pass

        return DraftResponse(
            description=req.description,
            draft=final_draft,
            sources=[
                SearchSource(
                    filename=r["metadata"]["filename"],
                    category=r["metadata"]["category"],
                    score=round(r["score"], 3),
                )
                for r in results
            ],
            review=review_report,
            fact_manifest=manifest.to_dict(),
            provenance_report=provenance,
            procedural_posture=posture.to_dict(),
            ground_traceability=[g.to_dict() for g in grounds_plan],
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Documents] Unhandled error: {e}")
        raise HTTPException(status_code=500, detail="Draft generation failed. Please try again.")


@router.post("/scan-contradictions", response_model=ContradictionResponse)
def scan_contradictions(
    req: ContradictionRequest,
    current_user: User = Depends(get_current_user)
):
    if not req.document_a.strip() or not req.document_b.strip():
        raise HTTPException(
            status_code=400,
            detail="Both Document A and Document B must have content"
        )

    result = find_contradictions(req.document_a, req.document_b)

    contradictions = [
        ContradictionPoint(**c)
        for c in result.get("contradictions", [])
    ]

    return ContradictionResponse(
        total_contradictions=result.get("total_contradictions", 0),
        contradictions=contradictions,
        overall_compatibility=result.get("overall_compatibility", "Unable to determine"),
    )