import re
import json
from typing import Dict, Any, List, Optional
from services.llm import call_llm
from services.rag import search_drafts
from models.review_models import (
    ReviewResponse, ReviewIssue, MissingField, FixResponse
)

PLACEHOLDER_PATTERNS = [
    re.compile(r"\[([A-Z0-9_\s/\-]{2,40})\]"),  # e.g. [PARTY NAME], [DATE]
    re.compile(r"<([A-Z0-9_\s/\-]{2,40})>"),    # e.g. <Insert Amount>
    re.compile(r"__(?:_{2,20})"),               # e.g. _______
]


def classify_document_type(text: str, user_hint: Optional[str] = None) -> str:
    """
    Step 1: Automatically detects document type from user hint, text title/preamble, or LLM fallback.
    """
    if user_hint and user_hint.strip() and user_hint.lower() != "auto":
        return user_hint.strip()

    text_head = text[:800].lower()

    # Common Indian legal document patterns
    if (
        "bail" in text_head
        or "section 437" in text_head or "section 439" in text_head  # Legacy CrPC
        or "section 480" in text_head or "section 483" in text_head  # BNSS regular bail
        or "section 482" in text_head  # BNSS anticipatory bail
        or "section 187" in text_head  # BNSS default bail
        or "section 478" in text_head  # BNSS bailable offences
    ):
        return "Bail Application"
    if "non-disclosure" in text_head or "nda" in text_head or "confidentiality" in text_head:
        return "NDA / Confidentiality Agreement"
    if "lease" in text_head or "tenancy" in text_head or "rent agreement" in text_head:
        return "Lease / Rent Agreement"
    if "affidavit" in text_head or "solemnly affirm" in text_head:
        return "Affidavit"
    if "legal notice" in text_head or "demand notice" in text_head:
        return "Legal Notice"
    if "power of attorney" in text_head or "poa" in text_head:
        return "Power of Attorney"
    if "sale deed" in text_head or "conveyance" in text_head:
        return "Sale Deed"
    if "employment" in text_head or "appointment" in text_head:
        return "Employment Agreement"
    if "memorandum of understanding" in text_head or "mou" in text_head:
        return "Memorandum of Understanding"
    if "partition deed" in text_head or "partition" in text_head:
        return "Partition Deed"
    if "mortgage" in text_head or "hypothecation" in text_head:
        return "Mortgage / Hypothecation Deed"
    if "vakalatnama" in text_head:
        return "Vakalatnama"

    # Fast LLM Classification fallback
    system_prompt = """Classify the following legal text into a standard legal document title (e.g. 'Partnership Deed', 'Bail Application', 'NDA', 'Affidavit', 'Service Agreement', 'Legal Notice', 'Writ Petition').
Respond ONLY with the document title name (max 4 words)."""
    try:
        raw_res = call_llm(system_prompt, f"Text sample:\n{text[:1000]}")
        return raw_res.strip().title()
    except Exception:
        return "Legal Document"


def extract_placeholders(text: str) -> List[MissingField]:
    """
    Step 3 / 4: Identifies missing mandatory placeholders ([DATE], [PARTY NAME], etc.).
    """
    missing_fields: List[MissingField] = []
    seen = set()
    lines = text.split("\n")

    for idx, line in enumerate(lines, 1):
        for pattern in PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(line):
                ph_raw = match.group(0)
                if ph_raw not in seen:
                    seen.add(ph_raw)
                    missing_fields.append(MissingField(
                        placeholder=ph_raw,
                        description=f"Unfilled placeholder '{ph_raw}' on line {idx}",
                        line_number=idx
                    ))
    return missing_fields


def extract_headings(text: str) -> List[str]:
    """Extracts clause titles and section headings from document text."""
    headings = []
    lines = text.split("\n")
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        # Match numbered clauses (1. SCOPE), Roman (I. PARTIES), uppercase headings (WHEREAS, PRAYER)
        if re.match(r"^(?:[0-9]+\.|\([a-z0-9]+\)|[I|V|X]+\.|\b[A-Z\s]{3,35}\b:?)", cleaned):
            headings.append(cleaned[:50])
    return headings


def run_hybrid_review(
    draft: str,
    document_hint: Optional[str] = None,
    fact_manifest = None,
    procedural_posture = None,
) -> ReviewResponse:
    """
    Generic 7-Step Universal Legal Review Pipeline:
    1. Detect document type
    2. Retrieve Top-5 most relevant templates from Qdrant
    3. Compare draft with retrieved reference templates
    4. Identify missing sections, clauses, structural differences, placeholders, formatting
    5. LLM reasoning (legal quality, weak arguments, risk analysis, no rewriting)
    6. Structured review report output
    """
    if not draft or not draft.strip():
        return ReviewResponse(
            document_type="Unknown",
            overall_score=0,
            risk_level="High",
            summary="Draft text is empty.",
            critical=[ReviewIssue(id="EMPTY", category="critical", title="Empty Draft", description="No text provided for review.")],
            warnings=[], suggestions=[], missing_sections=[], missing_fields=[]
        )

    # 1. Detect Document Type
    doc_type = classify_document_type(draft, document_hint)

    # 2. Retrieve Top-5 Most Relevant Templates from Qdrant
    search_query = f"{doc_type}\n{draft[:600]}"
    qdrant_results = search_drafts(search_query, n_results=5)
    if not qdrant_results:
        qdrant_results = search_drafts(draft[:400], n_results=5)

    ref_templates_text = "\n\n---\n\n".join([
        f"Reference Template ({r['metadata']['category']} - {r['metadata']['filename']}):\n{r['text']}"
        for r in qdrant_results
    ]) if qdrant_results else "No reference template retrieved."

    # 3 & 4. Deterministic Checks (Placeholders, Heading Comparisons, Execution Blocks)
    missing_fields = extract_placeholders(draft)
    draft_headings = extract_headings(draft)

    # Execution block check — only relevant for deeds, agreements, contracts, not bail/petitions
    EXECUTION_REQUIRED_TYPES = (
        "deed", "agreement", "contract", "nda", "mou", "affidavit",
        "power of attorney", "sale deed", "lease", "employment", "partnership"
    )
    doc_type_lower = doc_type.lower()
    needs_execution_block = any(t in doc_type_lower for t in EXECUTION_REQUIRED_TYPES)

    has_execution = any(
        kw in draft.lower()
        for kw in ["signature", "signed", "in witness whereof", "executed by", "deponent"]
    )



    # 5. LLM Comparison & Legal Quality Reasoning
    system_prompt = f"""You are a Senior Indian Legal Reviewer performing a comprehensive review of a {doc_type}.

You are provided with:
1. The User's Draft
2. Top-5 Retrieved Landmark Reference Templates from Qdrant

YOUR TASK:
Compare the User's Draft against the Top-5 Reference Templates to evaluate:
1. Missing essential sections or clauses present in standard reference templates
2. Structural differences or formatting inconsistencies (e.g. missing execution block, unnumbered clauses)
3. Legal quality, strength of arguments/grounds, and ambiguous phrasing
4. Substantive legal risk analysis

CRITICAL CONSTRAINTS:
- Do NOT rewrite the document.
- Base structural expectations on the retrieved Top-5 templates.
- Output MUST be valid JSON strictly adhering to this schema:
{{
  "summary": "2-sentence executive legal review summary",
  "missing_sections": ["Section / Clause 1", "Section / Clause 2"],
  "critical": [
     {{"id": "CRIT_1", "category": "critical", "title": "Title", "description": "Legal/structural deficiency", "suggested_fix": "Remedial action"}}
  ],
  "warnings": [
     {{"id": "WARN_1", "category": "warning", "title": "Title", "description": "Minor omission/ambiguity", "suggested_fix": "Remedial action"}}
  ],
  "suggestions": [
     {{"id": "SUGG_1", "category": "suggestion", "title": "Title", "description": "Style/drafting tip", "suggested_fix": "Remedial action"}}
  ]
}}"""


    user_msg = f"""Document Type: {doc_type}

User Draft to Review:
{draft[:2500]}

Reference Structure Highlights:
{ref_templates_text[:1200]}"""

    summary_text = ""
    missing_sections = []
    critical_issues: List[ReviewIssue] = []
    warning_issues: List[ReviewIssue] = []
    suggestion_issues: List[ReviewIssue] = []

    # Check execution block deterministically if missing
    if needs_execution_block and not has_execution:
        warning_issues.append(ReviewIssue(
            id="MISSING_EXECUTION",
            category="warning",
            title="Missing Execution / Signature Block",
            description="The document lacks a formal signature, witness, or advocate execution block.",
            suggested_fix="Add execution block with signature lines for parties/deponent and witnesses."
        ))

    # ── Deterministic Procedural Posture Checks ──
    draft_lower = draft.lower()
    if procedural_posture:
        if procedural_posture.relief_type == "regular_bail":
            if any(k in draft_lower for k in ["482 bnss", "section 482", "438 crpc", "section 438", "anticipatory bail"]):
                critical_issues.append(ReviewIssue(
                    id="PROCEDURAL_POSTURE_MISMATCH",
                    category="critical",
                    title="Procedural Posture Mismatch: Anticipatory vs Regular Bail",
                    description="The matter is Regular Bail (custody), but the draft invokes Anticipatory Bail provisions (Section 482 BNSS / 438 CrPC). Do not use provisions governing one type of relief for another.",
                    suggested_fix="Replace with governing regular bail provision (Section 483 BNSS / 439 CrPC)."
                ))
        elif procedural_posture.relief_type == "anticipatory_bail":
            if any(k in draft_lower for k in ["483 bnss", "section 483", "439 crpc", "section 439", "judicial custody", "in custody since"]):
                critical_issues.append(ReviewIssue(
                    id="PROCEDURAL_POSTURE_MISMATCH",
                    category="critical",
                    title="Procedural Posture Mismatch: Regular vs Anticipatory Bail",
                    description="The matter is Anticipatory Bail (pre-arrest), but the draft cites Regular Bail provisions (Section 483 BNSS / 439 CrPC) or asserts the accused is in custody.",
                    suggested_fix="Re-frame under Section 482 BNSS / 438 CrPC (apprehending arrest, not in custody)."
                ))

    # ── Deterministic Anti-Hallucination & Negative Assertion Checks ──
    if fact_manifest:
        provided_keys = {f.field_name: f.value for f in fact_manifest.provided_facts if f.value}

        # Antecedents check: [NOT PROVIDED] means unknown, not "no"!
        if "criminal_antecedents" not in provided_keys:
            if any(p in draft_lower for p in ["no criminal antecedents", "clean antecedents", "never been convicted", "no prior convictions", "no previous criminal history", "clean record", "unblemished record"]):
                critical_issues.append(ReviewIssue(
                    id="UNSUPPORTED_NEGATIVE_ANTECEDENTS",
                    category="critical",
                    title="Unknown Converted to Negative Assertion (Antecedents)",
                    description="Draft asserts accused has clean antecedents / no convictions, but antecedents were NOT provided in manifest. [NOT PROVIDED] means unknown, not 'no'.",
                    suggested_fix="Omit claim of clean antecedents or mark [CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS: Criminal antecedents unknown]."
                ))

        # Prolonged custody check:
        if "custody_duration" not in provided_keys and "arrest_date" not in provided_keys:
            if any(p in draft_lower for p in ["prolonged custody", "prolonged incarceration", "languishing in jail", "in custody for a long period"]):
                critical_issues.append(ReviewIssue(
                    id="UNSUPPORTED_PROLONGED_CUSTODY",
                    category="critical",
                    title="Unsupported Ground: Prolonged Detention",
                    description="Draft argues prolonged custody/incarceration, but custody duration and arrest date are unknown.",
                    suggested_fix="Omit prolonged custody argument or mark [CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS: Custody duration unknown]."
                ))

        # Tampering assertion check:
        if "no possibility of witness tampering" in draft_lower or "there is no evidence of tampering" in draft_lower:
            warning_issues.append(ReviewIssue(
                id="UNSUPPORTED_TAMPERING_ASSERTION",
                category="warning",
                title="Unsupported Tampering Factual Assertion",
                description="Draft states 'there is no possibility/evidence of witness tampering' as a factual conclusion without evidence record verification.",
                suggested_fix="Reframe as an undertaking: 'The Applicant undertakes not to tamper with evidence or influence witnesses.'"
            ))

    try:
        raw_llm_json = call_llm(system_prompt, user_msg, json_mode=True)
        clean_json = raw_llm_json
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].strip()

        parsed = json.loads(clean_json)
        summary_text = parsed.get("summary", "")
        missing_sections = parsed.get("missing_sections", [])

        for c in parsed.get("critical", []):
            critical_issues.append(ReviewIssue(**c))
        for w in parsed.get("warnings", []):
            warning_issues.append(ReviewIssue(**w))
        for s in parsed.get("suggestions", []):
            suggestion_issues.append(ReviewIssue(**s))
    except Exception as e:
        print(f"[ReviewEngine] Generic LLM comparison error: {e}")

    # 6. Score & Risk Assessment
    base_score = 100
    base_score -= len(critical_issues) * 15
    base_score -= len(warning_issues) * 7
    base_score -= len(suggestion_issues) * 3
    base_score -= len(missing_sections) * 8
    # Cap missing fields penalty so [NOT PROVIDED] / [REQUIRES VERIFICATION] markers
    # (which are grounded behaviors, not hallucinations) do not brand the draft as High Risk.
    base_score -= min(15, len(missing_fields) * 2)

    overall_score = max(15, min(100, base_score))

    if overall_score >= 85 and len(critical_issues) == 0:
        risk_level = "Low"
    elif overall_score >= 60 and len(critical_issues) <= 1:
        risk_level = "Medium"
    else:
        risk_level = "High"

    if not summary_text:
        summary_text = f"{doc_type} review completed against top Qdrant reference templates. Found {len(critical_issues)} critical issues and {len(missing_sections)} missing sections."

    return ReviewResponse(
        document_type=doc_type,
        overall_score=overall_score,
        risk_level=risk_level,
        summary=summary_text,
        critical=critical_issues,
        warnings=warning_issues,
        suggestions=suggestion_issues,
        missing_sections=missing_sections,
        missing_fields=missing_fields
    )


def auto_fix_draft(
    draft: str,
    issues: List[Dict[str, Any]],
    missing_sections: List[str],
    missing_fields: List[Dict[str, Any]],
    doc_type: Optional[str] = None,
    fact_manifest = None,
    procedural_posture = None,
    grounds_plan = None,
) -> FixResponse:
    """
    Step 7: Auto-fixes ONLY detected issues while preserving original draft structure, clause numbering, and headings.
    """
    if not draft or not draft.strip():
        return FixResponse(corrected_draft=draft, changes_made=["Draft was empty."])

    # Infer document type if not explicitly passed
    if not doc_type:
        doc_type = classify_document_type(draft)

    # 1. Retrieve real case law from Indian Kanoon / CommonLII via scraper if needed
    case_law_text = "No additional case law retrieved."
    if missing_sections:
        case_query = f"{doc_type} {' '.join(missing_sections[:2])}".strip()
        try:
            from services.scraper import search_cases
            case_results = search_cases(case_query, max_results=2)
            if case_results:
                case_law_text = "\n".join(
                    f"- {c['title']} — {c['link']}" for c in case_results
                )
        except Exception as e:
            print(f"[ReviewEngine] Case law retrieval notice: {e}")

    # Build fact-manifest-aware fix prompt
    fact_manifest_block = ""
    if fact_manifest:
        fact_manifest_block = "\n\n" + fact_manifest.to_prompt_block()

    posture_block = ""
    if procedural_posture:
        posture_block = f"""
=========================================================
EXACT PROCEDURAL POSTURE & GOVERNING LAW
=========================================================
Relief: {procedural_posture.relief_label}
Posture: {procedural_posture.posture_status.upper()}
Governing Provision: {procedural_posture.governing_provision}
Enforce: Never cite anticipatory bail provisions in regular bail, or regular bail provisions in anticipatory bail."""

    system_prompt = f"""You are a senior Indian legal document editor.

Your task is to fix ONLY the reported defects in the legal draft provided below.

YOUR SINGLE MOST IMPORTANT RULE:
Every factual assertion in the draft must be traceable to the FACT MANIFEST below.
If the draft contains a factual claim that does NOT appear in the FACT MANIFEST as
a PROVIDED fact, you MUST replace it with [NOT PROVIDED] or [TO BE VERIFIED FROM RECORD].

A "factual claim" is any statement about the accused/applicant/party's specific
circumstances: arrest status, custody duration, investigation status, chargesheet
status, criminal antecedents, employment, address, family ties, medical condition,
evidence, recoveries, previous bail applications, etc.

A "legal submission" is a generic argument that does not assert specific facts:
"The applicant undertakes to cooperate with investigation" or "It is submitted that
the alleged offence is bailable in nature." These are acceptable drafting language.

=========================================================
CORE PRINCIPLE & GROUNDING MANDATE
=========================================================
NEVER FILL A KNOWLEDGE GAP WITH A PLAUSIBLE-SOUNDING LEGAL FACT.
Groundedness is more important than completeness.
Verification is more important than fluency.
Accuracy is more important than making the document look court-ready.

=========================================================
FACT GROUNDING & STATEMENT CLASSIFICATION (RULES 1, 2, 3)
=========================================================
Scan the ENTIRE draft for factual assertions. For each one:
- Only USER_FACT and DOCUMENT_FACT may be stated as facts about the case.
- If a fact is NOT in the FACT MANIFEST, replace with [NOT PROVIDED] or [REQUIRES VERIFICATION].
- Never confuse absence of data with absence of a fact:
  BAD: "There is no possibility of witness intimidation."
  GOOD: "No information was provided regarding witness intimidation."
- Never invent: arrest date, custody status, custody duration, FIR date,
  police station, district, chargesheet status, investigation status,
  trial stage, criminal antecedents, residence, employment, family circumstances,
  medical circumstances, evidence, witness status, recovery, previous bail history,
  co-accused status, defence facts.

=========================================================
LEGAL PROVISION VALIDATION (RULE 4)
=========================================================
- Never infer a statute solely from a section number.
- Never infer statute name, corresponding provision, amendment, repeal, or transition rule.
- If only a section number was provided, preserve Section [number] [STATUTE REQUIRES VERIFICATION].
- Do NOT silently convert an old statutory provision (IPC/CrPC) into a new statutory provision (BNS/BNSS).

=========================================================
PROCEDURAL STATUS (RULE 5)
=========================================================
Do NOT infer the procedural stage from the requested document type.
Requesting a bail application does NOT prove:
- accused is arrested or in custody
- investigation is complete or chargesheet filed
- trial commenced or charges framed
Only state these when supported by the FACT MANIFEST.

=========================================================
CASE LAW / CITATION INTEGRITY (RULE 6)
=========================================================
Never generate a citation merely because it looks plausible.
- If an unverified case is cited: [CITATION REQUIRES VERIFICATION]
- If a cited case does not support the attributed proposition: [PROPOSITION MISMATCH]
- Cite ONLY from the retrieved case law list below. Never fabricate SCC citations, URLs, dates, or quotations.

=========================================================
LEGAL PRINCIPLES & CASE-SPECIFIC GROUNDS (RULES 7, 8, 9)
=========================================================
- Do NOT overstate legal principles (avoid "statute guarantees", "entitled as of right", "court must").
- Do NOT generate case-specific grounds unless their factual basis exists (flight risk, witness tampering, prolonged custody, parity, delay, clean antecedents, medical hardship).
- If such a ground is relevant but cannot be established from the manifest, write:
  [CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS]
- Generic boilerplate must NOT be stated as fact:
  BAD: "The petitioner has strong family ties and therefore will not abscond."
  GOOD: "The applicant may rely on residential/family ties as a factor relevant to flight risk, subject to supporting facts being provided."

=========================================================
DOCUMENT TYPE INTEGRITY & DUPLICATE CHECK
=========================================================
- Bail Applications: NO agreement clauses, execution blocks, witness tables, WHEREAS, NOW THEREFORE.
- Contracts/Deeds: NO criminal grounds, bail prayers, court headers.
- Eliminate verbatim repeated paragraphs across different sections.{posture_block}

=========================================================
RETRIEVED CASE LAW
=========================================================
Cite from this list ONLY — never fabricate:

{case_law_text}{fact_manifest_block}"""


    issues_str = json.dumps({
        "critical_and_warnings": issues,
        "missing_sections": missing_sections,
        "missing_fields": missing_fields
    }, indent=2)

    user_msg = f"""Reported Issues & Missing Elements to Fix:
{issues_str}

Original Draft:
{draft}"""

    corrected_text = call_llm(system_prompt, user_msg)

    changes_summary = []
    if missing_sections:
        changes_summary.append(f"Inserted {len(missing_sections)} missing section(s): {', '.join(missing_sections)}")
    if missing_fields:
        changes_summary.append(f"Cleaned {len(missing_fields)} unfilled placeholder field(s)")
    if issues:
        changes_summary.append(f"Fixed {len(issues)} detected legal issue(s)")
    if not changes_summary:
        changes_summary.append("Refined legal terminology and structural formatting")

    return FixResponse(
        corrected_draft=corrected_text,
        changes_made=changes_summary
    )


def run_two_pass_refinement(
    initial_draft: str,
    category_hint: Optional[str] = None,
    fact_manifest = None,
    procedural_posture = None,
    grounds_plan = None,
) -> Dict[str, Any]:
    """
    Executes Review & Auto-Fix Refinement Loop:
    Evaluates initial draft, auto-fixes any detected defects, and returns the polished final draft and review.
    The optional fact_manifest enables hallucination-aware fixing — assertions not backed by provided facts
    are replaced with [NOT PROVIDED] rather than silently accepted.
    """
    if not initial_draft or not initial_draft.strip():
        return {
            "initial_draft": "",
            "final_draft": "",
            "pass1_score": 0,
            "pass2_score": 0,
            "review": None
        }

    print("[TwoPassRefinement] Starting Review & Analysis...")
    # PASS 1 REVIEW
    review_p1 = run_hybrid_review(
        initial_draft,
        category_hint,
        fact_manifest=fact_manifest,
        procedural_posture=procedural_posture,
    )
    all_issues_p1 = [i.model_dump() for i in review_p1.critical + review_p1.warnings + review_p1.suggestions]
    missing_sec_p1 = review_p1.missing_sections
    missing_fields_p1 = [f.model_dump() for f in review_p1.missing_fields]

    # Only auto-fix if critical issues or missing sections exist, or score is below 90
    if (review_p1.critical or missing_sec_p1 or review_p1.overall_score < 90) and len(initial_draft) > 50:
        print("[TwoPassRefinement] Deficiencies detected. Executing Auto-Fix...")
        try:
            fix_res = auto_fix_draft(
                initial_draft,
                all_issues_p1,
                missing_sec_p1,
                missing_fields_p1,
                doc_type=review_p1.document_type,
                fact_manifest=fact_manifest,
                procedural_posture=procedural_posture,
                grounds_plan=grounds_plan,
            )
            final_draft = fix_res.corrected_draft if fix_res and fix_res.corrected_draft else initial_draft
            final_review = run_hybrid_review(
                final_draft,
                category_hint,
                fact_manifest=fact_manifest,
                procedural_posture=procedural_posture,
            )
        except Exception as fix_err:
            print(f"[TwoPassRefinement] Auto-fix error: {fix_err}")
            final_draft = initial_draft
            final_review = review_p1
    else:
        print("[TwoPassRefinement] Initial draft is solid (Score 90+).")
        final_draft = initial_draft
        final_review = review_p1

    print(f"[TwoPassRefinement] Completed! Pass 1 Score: {review_p1.overall_score} -> Final Score: {final_review.overall_score}")

    return {
        "initial_draft": initial_draft,
        "final_draft": final_draft,
        "pass1_score": review_p1.overall_score,
        "pass2_score": final_review.overall_score,
        "review": final_review.model_dump()
    }

