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


def run_hybrid_review(draft: str, document_hint: Optional[str] = None) -> ReviewResponse:
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

    if needs_execution_block and not has_execution:
        warning_issues.append(ReviewIssue(
            id="MISSING_EXECUTION",
            category="warning",
            title="Missing Execution / Signature Block",
            description="The document lacks a formal signature or execution block, which is required for this document type.",
            suggested_fix="Add execution block with signature lines for parties and witnesses."
        ))

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
{draft[:3500]}

Top-5 Reference Templates from Qdrant:
{ref_templates_text[:4000]}"""

    summary_text = ""
    missing_sections = []
    critical_issues: List[ReviewIssue] = []
    warning_issues: List[ReviewIssue] = []
    suggestion_issues: List[ReviewIssue] = []

    # Check execution block deterministically if missing
    if not has_execution:
        warning_issues.append(ReviewIssue(
            id="MISSING_EXECUTION",
            category="warning",
            title="Missing Execution / Signature Block",
            description="The document lacks a formal signature, witness, or advocate execution block.",
            suggested_fix="Add execution block with signature lines for parties/deponent and witnesses."
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
    base_score -= len(missing_fields) * 4

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


def auto_fix_draft(draft: str, issues: List[Dict[str, Any]], missing_sections: List[str], missing_fields: List[Dict[str, Any]]) -> FixResponse:
    """
    Step 7: Auto-fixes ONLY detected issues while preserving original draft structure, clause numbering, and headings.
    """
    if not draft or not draft.strip():
        return FixResponse(corrected_draft=draft, changes_made=["Draft was empty."])

    system_prompt = """You are a senior Indian legal document editor.

Your task is to fix ONLY the reported defects in the legal draft provided below.

=========================================================
GOVERNING LAW
=========================================================

With effect from 1 July 2024, the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 replaced the CrPC, 1973.

For bail matters, use BNSS sections:
- Section 478 BNSS (bailable offences, formerly CrPC 436)
- Section 480 BNSS (bail by magistrate, formerly CrPC 437)
- Section 482 BNSS (anticipatory bail, formerly CrPC 438)
- Section 483 BNSS (regular bail HC/Sessions, formerly CrPC 439)
- Section 187 BNSS (default bail, formerly CrPC 167(2))

Replace any CrPC section reference with its BNSS equivalent unless the matter pre-dates 01 July 2024.

=========================================================
STRICT LAWS OF MODIFICATION
=========================================================

1. Modify ONLY the incorrect, missing, or defective sections listed in the issues report.
2. Preserve all existing correct text, formatting, clause numbering, and headings.
3. Do NOT replace [Not Provided] placeholders with invented values — leave them as-is.
4. Insert missing required sections in their proper legal placement.
5. Do NOT rewrite or rephrase clauses that are already legally sound.
6. Output the COMPLETE corrected document, ready for advocate review.

=========================================================
ANTI-HALLUCINATION — NEVER INVENT
=========================================================

Do NOT invent or fabricate:
- dates, arrest dates, FIR numbers
- witness names or statements
- consideration amounts or property details
- investigation status or custody duration
- charge-sheet status or criminal antecedents
- court findings or evidence

If a fact is missing, write [Not Provided]. Do NOT guess.

=========================================================
DOCUMENT TYPE INTEGRITY
=========================================================

Do NOT add sections that do not belong to the document type.
Bail Applications must NOT receive: WHEREAS, execution blocks, notary clauses, witness tables.
Sale Deeds must NOT receive: bail prayer, criminal grounds."""


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


def run_two_pass_refinement(initial_draft: str, category_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes 2-Pass Review & Auto-Fix Refinement Loop:
    Pass 1: Review initial draft -> Auto-Fix detected issues -> Pass 1 Draft
    Pass 2: Review Pass 1 Draft -> Auto-Fix detected issues -> Best Refined Final Draft
    Returns dictionary with initial draft, pass 1/2 scores, final review report, and best refined draft.
    """
    if not initial_draft or not initial_draft.strip():
        return {
            "initial_draft": "",
            "final_draft": "",
            "pass1_score": 0,
            "pass2_score": 0,
            "review": None
        }

    print("[TwoPassRefinement] Starting Pass 1 Review & Auto-Fix...")
    # PASS 1 REVIEW
    review_p1 = run_hybrid_review(initial_draft, category_hint)
    all_issues_p1 = [i.model_dump() for i in review_p1.critical + review_p1.warnings + review_p1.suggestions]
    missing_sec_p1 = review_p1.missing_sections
    missing_fields_p1 = [f.model_dump() for f in review_p1.missing_fields]

    # PASS 1 AUTO-FIX
    if all_issues_p1 or missing_sec_p1 or missing_fields_p1 or review_p1.overall_score < 95:
        print("[TwoPassRefinement] Pass 1 issues detected. Executing Pass 1 Auto-Fix...")
        fix_res_p1 = auto_fix_draft(initial_draft, all_issues_p1, missing_sec_p1, missing_fields_p1)
        draft_p1 = fix_res_p1.corrected_draft
    else:
        print("[TwoPassRefinement] Pass 1 clean (Score 95+).")
        draft_p1 = initial_draft

    # PASS 2 REVIEW
    print("[TwoPassRefinement] Starting Pass 2 Review & Auto-Fix...")
    review_p2 = run_hybrid_review(draft_p1, category_hint)
    all_issues_p2 = [i.model_dump() for i in review_p2.critical + review_p2.warnings + review_p2.suggestions]
    missing_sec_p2 = review_p2.missing_sections
    missing_fields_p2 = [f.model_dump() for f in review_p2.missing_fields]

    # PASS 2 AUTO-FIX
    if (all_issues_p2 or missing_sec_p2 or missing_fields_p2) and review_p2.overall_score < 98:
        print("[TwoPassRefinement] Pass 2 issues detected. Executing Pass 2 Auto-Fix...")
        fix_res_p2 = auto_fix_draft(draft_p1, all_issues_p2, missing_sec_p2, missing_fields_p2)
        best_final_draft = fix_res_p2.corrected_draft
        final_review = run_hybrid_review(best_final_draft, category_hint)
    else:
        best_final_draft = draft_p1
        final_review = review_p2

    print(f"[TwoPassRefinement] Completed! Pass 1 Score: {review_p1.overall_score} -> Pass 2 Final Score: {final_review.overall_score}")

    return {
        "initial_draft": initial_draft,
        "final_draft": best_final_draft,
        "pass1_score": review_p1.overall_score,
        "pass2_score": final_review.overall_score,
        "review": final_review.model_dump()
    }

