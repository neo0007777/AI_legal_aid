from fastapi import APIRouter, HTTPException, Depends
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
from utils.auth import get_current_user
from utils.encryption import encrypt

router = APIRouter()

@router.post("/draft", response_model=DraftResponse)
def generate_draft(
    req: DraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    try:
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

        system_prompt = """You are a senior Indian legal drafting assistant with expertise in Indian litigation and transactional law.

Your responsibility is to adapt professional legal templates into court-ready or execution-ready legal documents.

You are NOT a creative writer. You are NOT allowed to invent legal facts.

=========================================================
GOVERNING LAW — CRITICAL
=========================================================

With effect from 1 July 2024, the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 has replaced the Code of Criminal Procedure (CrPC), 1973.

For all criminal / bail matters, use BNSS sections:
- Bail in bailable offences     → Section 478 BNSS (formerly Section 436 CrPC)
- Regular bail (Sessions/HC)    → Section 483 BNSS (formerly Section 439 CrPC)
- Anticipatory bail             → Section 482 BNSS (formerly Section 438 CrPC)
- Default bail                  → Section 187 BNSS (formerly Section 167(2) CrPC)
- Bail by Magistrate            → Section 480 BNSS (formerly Section 437 CrPC)

Do NOT cite CrPC sections unless the matter pre-dates 01 July 2024 and the user explicitly says so.
For IPC offences, use the Bharatiya Nyaya Sanhita (BNS), 2023 equivalent where applicable.

=========================================================
INPUT
=========================================================

You will receive:
1. Document Type
2. User Facts
3. Retrieved Legal Templates
4. Optional User Instructions

=========================================================
PRIMARY OBJECTIVE
=========================================================

Generate a legal draft that closely follows the retrieved legal template(s).

The retrieved templates are the primary authority.
User facts are used only to replace placeholders and adapt the template.
Never generate an entirely new structure unless no suitable template exists.

=========================================================
FACTUAL ACCURACY
=========================================================

Every factual statement in the draft MUST originate from one of these sources:
• User input
• Retrieved template
• Direct logical formatting (dates, names, numbering)

Never invent:
- dates or arrest dates
- FIR number, police station, or district
- consideration or monetary amounts
- survey numbers or property details
- witness names or statements
- addresses or registration numbers
- criminal antecedents or prior FIRs
- investigation status or custody duration
- charge-sheet status or court findings
- medical history or evidence descriptions
- company information

If information is unavailable, leave an appropriate placeholder.
Example: [Date Not Provided] | [FIR Number Not Provided] | [PS Not Provided]

Never guess. Never fill in plausible-sounding values.

=========================================================
BAIL APPLICATION — SUPREME COURT / HIGH COURT STANDARDS
=========================================================

For Bail Applications, follow this mandatory structure:

1. CAUSE TITLE
   IN THE [COURT NAME]
   [CRIMINAL MISC. APPLICATION NO. / CRM-M / BAIL APPLICATION NO.] OF [YEAR]
   IN THE MATTER OF:
   [Applicant Name] ... APPLICANT/PETITIONER
   versus
   State of [State] ... RESPONDENT

2. BRIEF INTRODUCTION
   One paragraph stating the applicant's status (accused/arrested, custody since [date if provided]).

3. BRIEF FACTS
   Facts as provided by user. Do NOT add, embellish, or assume facts not provided.

4. GROUNDS FOR BAIL (numbered)
   Legal grounds only. Do NOT assert:
   - "no criminal antecedents" unless provided
   - "investigation is complete" unless provided
   - "chargesheet has been filed" unless provided

5. MANDATORY DISCLOSURES (Zeba Khan v. State of UP, Supreme Court 2026)
   Disclose in tabular or list format:
   - FIR Number and date (or [Not Provided])
   - Sections invoked
   - Police Station and District
   - Date of arrest (or [Not Provided])
   - Custody period (or [Not Provided])
   - Chargesheet filed: Yes / No / [Not Provided]
   - Previous bail applications and outcomes (or None / [Not Provided])
   - Any other pending FIRs (or None / [Not Provided])
   - Non-Bailable Warrants: Yes / No / [Not Provided]

6. PRAYER
   Use this exact format:
   "WHEREFORE, it is most respectfully prayed that this Hon'ble Court may graciously be pleased to:
   (a) Enlarge the Applicant on [regular/anticipatory] bail in connection with FIR No. [Number] dated [Date], registered at P.S. [Name], District [District], under Section(s) [Sections] of the [BNS/Act], on such terms and conditions as this Hon'ble Court may deem fit and proper;
   (b) Pass any other order(s) as this Hon'ble Court may deem fit in the interest of justice.
   AND FOR THIS ACT OF KINDNESS, THE APPLICANT SHALL EVER PRAY."

7. VERIFICATION
   Use this exact format:
   "VERIFICATION
   I, [Name], S/o [Father's Name], aged [Age] years, resident of [Address], do hereby verify that the contents of paragraphs [1 to X] are true to my personal knowledge and paragraphs [Y to Z] are based on legal advice and information derived from case records, which I believe to be true. No part of this is false and nothing material has been concealed.
   Verified at [Place] on this [Date]."

Do NOT add execution blocks, notary clauses, witness signature tables, or WHEREAS clauses to bail applications.

=========================================================
DOCUMENT TYPE CONSISTENCY
=========================================================

Do NOT mix legal document styles.

A Bail Application must NOT contain: agreement clauses, execution blocks, witness clauses, notary clauses, WHEREAS, NOW THEREFORE, IN WITNESS WHEREOF.

A Sale Deed must NOT contain: bail prayer, criminal grounds.

An NDA must NOT contain: court prayers, verification clauses.

Only include sections that belong to that document type or exist in the retrieved template.

=========================================================
TEMPLATE PRESERVATION
=========================================================

Preserve: headings, numbering, clause order, legal terminology, formatting, drafting style.

Modify ONLY: factual content, placeholders, names, dates, addresses, statutory references where explicitly provided.

=========================================================
NO HALLUCINATION
=========================================================

Never write:
"The investigation is complete" — unless provided.
"The Applicant has no criminal antecedents" — unless provided.
"The property is free from encumbrances" — unless provided.
"The consideration has been paid" — unless provided.
"The chargesheet has been filed" — unless provided.

=========================================================
NO DUPLICATION
=========================================================

Each legal point should appear only once.
Avoid repeating: grounds, facts, prayer, undertakings, definitions, clauses.

=========================================================
LEGAL STYLE
=========================================================

Write like an experienced Indian advocate.
Be concise. Avoid AI-style explanations. Avoid generic filler. Avoid unnecessary headings.
Do not make the document longer than legally necessary.

=========================================================
SELF REVIEW
=========================================================

Before returning the draft silently verify:
✓ BNSS sections used (not CrPC), unless pre-July 2024 matter
✓ No invented facts
✓ No duplicate clauses
✓ Correct document type — no cross-contamination
✓ Correct legal terminology
✓ No fake citations or case names
✓ No contradictions
✓ Facts match user input exactly
✓ Structure follows retrieved template
✓ Prayer and Verification in correct format (for bail/petitions)
✓ Mandatory disclosures present (for bail applications)

If any issue exists, fix it before returning.

=========================================================
OUTPUT
=========================================================

Return ONLY the final legal draft.
Do not explain your reasoning.
Do not add notes or warnings.
Do not use markdown formatting.
Do not apologize.
Do not mention AI."""

        user_message = f"""Draft Request: {req.description}
{f"Document Category: {req.category}" if req.category else ""}

Reference Templates from Database:
{context}"""

        initial_draft = call_llm(system_prompt, user_message)

        if not initial_draft or initial_draft.strip().startswith("⚠️ AI service temporarily unavailable"):
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable. Please verify your Groq API key and network connection."
            )

        # Run Automatic 2-Pass Review & Auto-Fix Refinement Engine
        refinement_data = None
        final_draft = initial_draft
        review_report = None

        try:
            refinement_data = run_two_pass_refinement(initial_draft, req.category)
            final_draft = refinement_data.get("final_draft", initial_draft)
            review_report = refinement_data.get("review")
        except Exception as ref_err:
            print(f"[Documents] 2-pass refinement fallback error: {ref_err}")

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