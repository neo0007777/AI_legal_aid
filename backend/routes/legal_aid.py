import json
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from models.database import get_db, User, QueryLog, LegalAidMemory
from models.schemas import (
    LegalAidRequest, LegalAidResponse, SearchSource,
    LegalAidMemoryRequest, LegalAidMemoryResponse
)

from services.rag import search_drafts
from services.llm import call_llm
from utils.auth import get_current_user, get_optional_current_user
from utils.encryption import encrypt
from services.scraper import scrape_indian_kanoon
from services.pdf_generator import generate_legal_aid_pdf

router = APIRouter()

NON_LEGAL_PATTERNS = [
    # Code generation and programming requests
    r"\b(write|create|generate|give\s+me|build|provide|show|share)\s+(a\s+)?(python|javascript|java|c\+\+|c#|golang|rust|html|css|sql|bash|shell|node|php|react)\s*(code|script|program|function|app)?\b",
    r"\b(write|create|generate|provide)\s+(a\s+)?(code|script|program|software|algorithm)\b",
    r"\b(python|javascript|java|c\+\+|bash)\s+(code|script|program)\b",
    r"^(write\s+python|python\s+code|write\s+code|give\s+code|script\s+for|code\s+for)\b",
    r"\b(how\s+to\s+code|debug|fix\s+my\s+code|compile|syntax\s+error|pip\s+install|npm\s+install)\b",
    # Non-legal creative writing and general topics
    r"\b(write\s+a\s+(poem|song|story|essay|joke|script\s+for\s+a\s+movie))\b",
    r"\b(recipe\s+for|how\s+to\s+cook|how\s+to\s+bake|ingredients\s+for)\b",
    r"\b(solve\s+this\s+(math|equation|algebra|calculus))\b",
    r"\b(weather\s+in|who\s+won\s+the\s+match|cricket\s+score|movie\s+recommendation)\b",
]

SUBSTANCE_OR_EXTREME_PATTERNS = [
    # Drugs, substances, narcotics (e.g. "i smoke weed and all", "weed", "ganja")
    r"\b(smoke|smoking|consume|consuming|buy|buying|selling|sell|use|using|do|doing|take|taking|possess|possession\s+of|carry|carrying)\s+.*?(weed|ganja|charas|marijuana|cannabis|pot|hash|hashish|bhang|cocaine|heroin|lsd|mdma|ecstasy|meth|chitta|drugs|narcotics|contraband)\b",
    r"\b(i\s+(smoke|take|do|use|have|consume|buy|sell)\s+(weed|drugs|ganja|charas|marijuana|pot|narcotics|substances?))\b",
    r"\b(weed|ganja|charas|marijuana|cannabis|pot|hashish|cocaine|heroin|narcotic|narcotics|mdma|methamphetamine)\b",
    r"\b(ndps\s+act|banned\s+drugs|illicit\s+substance|narcotic\s+drugs)\b",
    # Extreme ethically sensitive / penal / dangerous acts
    r"\b(drunk\s+driv(ing|e)|drink\s+and\s+drive|dui|dwi)\b",
    r"\b(suicide|kill\s+myself|end\s+my\s+life|self[- ]harm)\b",
    r"\b(prostitution|call\s+girl|escort\s+service|sex\s+traffick(ing)?)\b",
    r"\b(illegal\s+gambling|cricket\s+betting|satta|matka)\b",
    r"\b(dark\s+web|buy\s+weapons?|illegal\s+arms|buy\s+gun)\b",
]

ILLEGAL_FACILITATION_PATTERNS = [
    r"\b(how\s+to|how\s+can\s+i|help\s+me|ways\s+to|tricks?\s+to)\s+(bribe|pay\s+bribe|take\s+bribe|give\s+bribe)\b",
    r"\b(how\s+to|how\s+can\s+i|help\s+me|ways\s+to)\s+(forge|fabricate|counterfeit|falsify)\b",
    r"\b(fake\s+(passport|aadhaar|pan|degree|stamp|signature|bill|invoice|receipt|document))\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(evade|avoid|escape)\s+(arrest|police|warrant|ed|cbi|custody)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(hide|convert|clean|launder)\s+(black\s+money|ill-gotten|unaccounted\s+cash|unexplained\s+money)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(evade\s+tax|tax\s+evasion|evade\s+gst|cheat\s+on\s+taxes)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(hack|crack|steal|infiltrate)\s+(phone|whatsapp|account|email|bank|data|password)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(kill|murder|poison|harm|assault|threaten|extort|blackmail)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(destroy|tamper\s+with|hide)\s+(evidence|proof|weapon|cctv)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(threaten|bribe|influence|pressure)\s+(witness|judge|investigator|police)\b",
    r"\b(how\s+to|how\s+can\s+i)\s+(smuggle|deal\s+in|sell)\s+(drugs|weapons|narcotics|contraband)\b",
    r"\b(money\s+laundering|hawala|benami\s+transaction)\b",
]

NON_LEGAL_ANSWER = """DIRECT ANSWER:
LexSetu is exclusively an Indian legal intelligence platform. We only reply to legal questions, statutory research inquiries, and court procedural matters. We do not generate programming code, software scripts, or non-legal general technical solutions.

LEGAL BASIS:
Platform Domain Scope: LexSetu Legal Intelligence Terms of Service.

BINDING PRECEDENTS:
Not applicable for non-legal software or coding requests.

ACTIONABLE INSIGHT:
Please ask a question regarding Indian law—such as provisions under the Bharatiya Nyaya Sanhita (BNS), Code of Civil Procedure (CPC), Bharatiya Nagarik Suraksha Sanhita (BNSS), contract enforceability, bail procedure, consumer rights, or judicial precedents. For software development or coding scripts, please consult general programming tools.

DISCLAIMER:
LexSetu standard tier is strictly dedicated to Indian legal aid, statutory provisions, and judicial research."""

SUBSTANCE_OR_EXTREME_UPGRADE_ANSWER = """DIRECT ANSWER:
Your current plan does not allow answering this question.

Inquiries regarding illicit substances (such as weed, cannabis, narcotics under the Narcotic Drugs and Psychotropic Substances Act, 1985), sensitive ethical conduct, or active personal penal liabilities cannot be addressed under the standard AI Legal Aid plan.

To receive guidance on sensitive penal exposure, statutory defense safeguards, or to hold privileged consultations with an advocate, please upgrade your plan to the LexSetu Advocate Pro tier. Under Section 126 of the Indian Evidence Act, 1872 / Section 132 of the Bharatiya Sakshya Adhiniyam, 2023, communications concerning criminal liabilities and defense must remain strictly confidential and privileged.

LEGAL BASIS:
Narcotic Drugs and Psychotropic Substances (NDPS) Act, 1985 (Sections 20, 27); Bharatiya Nyaya Sanhita (BNS), 2023; Bar Council of India Standards of Professional Conduct; Section 126 Evidence Act / Section 132 Bharatiya Sakshya Adhiniyam, 2023.

BINDING PRECEDENTS:
Tofan Singh v. State of Tamil Nadu, (2021) 4 SCC 1 – Supreme Court ruling affirming that sensitive penal liabilities and evidentiary safeguards in substance offenses require confidential advocate representation and strict constitutional compliance.

ACTIONABLE INSIGHT:
1. Plan Limitation: Your current plan does not permit answering inquiries involving illicit substances, personal penal exposure, or ethically compromised conduct.
2. Upgrade Your Plan: Upgrade to the LexSetu Advocate Pro / Criminal Defense Tier to access privileged case audits, statutory defense analysis under Section 37 NDPS, and 1-on-1 strategy sessions with empanelled Senior Criminal Defense Advocates.
3. Due Process Rights: If subject to any inquiry or notice by law enforcement authorities, invoke your constitutional right to legal counsel under Article 22(1) of the Constitution of India.

DISCLAIMER:
Your current plan does not allow answering questions regarding active substance use or penal conduct. Please upgrade your plan to access privileged criminal defense counsel."""

UNLAWFUL_UPGRADE_ANSWER = """DIRECT ANSWER:
Your current plan does not allow answering this inquiry.

Inquiries involving active penal exposure, regulatory enforcement defense, or sensitive criminal defense strategies cannot be addressed under the standard AI Legal Aid tier.

Please upgrade your plan to LexSetu Advocate Pro to access confidential legal advisory under Section 126 of the Indian Evidence Act / Section 132 of the Bharatiya Sakshya Adhiniyam, 2023.

LEGAL BASIS:
Bharatiya Nyaya Sanhita (BNS), 2023; Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023; Bar Council of India Standards of Professional Conduct; Constitution of India, Article 22(1).

BINDING PRECEDENTS:
State of Punjab v. Davinder Pal Singh Bhullar, (2011) 14 SCC 770 – Supreme Court ruling affirming that legal advisory must strictly adhere to statutory due process and constitutional bounds.

ACTIONABLE INSIGHT:
1. Plan Limitation: Your current standard plan does not allow advisory on active penal exposure or defense facilitation.
2. Upgrade Your Plan: Upgrade to LexSetu Advocate Pro to unlock privileged case consultations, limitation analysis, and confidential defense advisory with empanelled High Court advocates.
3. Due Process: In any legal investigation, always seek formal advocate representation to protect constitutional rights.

DISCLAIMER:
LexSetu standard plan provides statutory civil and general legal research only. Upgrade your plan for privileged criminal defense counsel."""


def is_non_legal_query(question: str) -> bool:
    q = question.lower().strip()
    return any(re.search(pat, q) for pat in NON_LEGAL_PATTERNS)


def is_substance_or_extreme_query(question: str) -> bool:
    q = question.lower().strip()
    return any(re.search(pat, q) for pat in SUBSTANCE_OR_EXTREME_PATTERNS)


def is_unlawful_query(question: str) -> bool:
    q = question.lower().strip()
    return any(re.search(pat, q) for pat in ILLEGAL_FACILITATION_PATTERNS)


STRUCTURE_TITLES = {
    "standard": "Standard Judicial",
    "executive_brief": "Executive Legal Brief",
    "irac": "IRAC Framework (Issue, Rule, Application, Conclusion)",
    "bullet_points": "Actionable Bullet Points & Checklist",
    "custom": "Custom Guided Structure",
}


def detect_structure_from_query(question: str) -> tuple[Optional[str], Optional[str]]:
    """
    Detects if the user explicitly guided the format/structure inside their question text.
    Returns (detected_mode, custom_instructions).
    """
    q_lower = question.lower()
    if re.search(r"\b(irac|issue\s+rule\s+application)\b", q_lower):
        return "irac", None
    if re.search(r"\b(executive\s+brief|executive\s+summary\s+format|brief\s+for\s+board)\b", q_lower):
        return "executive_brief", None
    if re.search(r"\b(in\s+bullets?|bullet\s+points?|bulleted|checklist\s+format)\b", q_lower):
        return "bullet_points", None

    # Check for direct custom guidance like "format as:", "structure as:", "give me in table", "only 3 points"
    format_guide_match = re.search(
        r"\b(format\s+(it\s+)?as|structure\s+(it\s+)?as|give\s+(it\s+)?in|present\s+(it\s+)?as|in\s+the\s+form\s+of)\s*[:\-]?\s*([^\.\n]+)",
        q_lower,
    )
    if format_guide_match:
        guidance = format_guide_match.group(0).strip()
        return "custom", guidance

    return None, None


def build_structure_prompt_instructions(structure_mode: str, custom_instructions: Optional[str]) -> str:
    """
    Dynamically generates the structural prompt contract for the LLM based on user preferences or memory.
    """
    if structure_mode == "executive_brief":
        return """You MUST structure your response as an EXECUTIVE LEGAL BRIEF for counsel and leadership:
EXECUTIVE SUMMARY:
[2-3 punchy, high-impact sentences stating the core legal holding, commercial/personal impact, and direct answer]

STATUTORY POSITION:
[Codified provisions under relevant Indian Acts (e.g. BNS, BNSS, CPC, NI Act) with exact section titles]

JUDICIAL PRECEDENTS:
[Binding landmark Supreme Court and High Court precedents upholding this posture, with citation and ratio]

STRATEGIC RECOMMENDATIONS:
[Actionable operational steps, mitigation precautions, and statutory limitation deadlines]

DISCLAIMER:
This is for informational purposes only. Please consult a qualified advocate for formal court representation."""

    elif structure_mode == "irac":
        return """You MUST structure your response using the formal legal IRAC (Issue, Rule, Application, Conclusion) methodology:
LEGAL ISSUE:
[The specific questions of Indian law and controversy presented]

RULE:
[Governing statutory provisions, codified sections, and established legal tests/ratios in Indian jurisprudence]

APPLICATION:
[Rigorous legal analysis applying the statutory rules and precedents directly to the factual inquiry]

CONCLUSION:
[Definitive legal conclusion, remedies available, and procedural next steps]

DISCLAIMER:
This is for informational purposes only. Please consult a qualified advocate for formal court representation."""

    elif structure_mode == "bullet_points":
        return """You MUST structure your response cleanly into clear, scannable BULLET POINTS & CHECKLIST:
KEY SUMMARY:
[1 concise paragraph summarizing the bottom-line legal answer]

STATUTORY PROVISIONS (BULLETS):
• [Section and Act name]: [Concise explanation of legal mandate]
• [Section and Act name]: [Concise explanation of legal mandate]

LANDMARK PRECEDENTS (BULLETS):
• [Case Name (Year Citation)]: [Core binding holding]

ACTIONABLE CHECKLIST:
1. [First procedural or documentary step with timeline]
2. [Second procedural step]
3. [Third procedural step]

DISCLAIMER:
This is for informational purposes only. Please consult a qualified advocate for formal court representation."""

    elif structure_mode == "custom" and custom_instructions:
        return f"""CRITICAL USER GUIDANCE - CUSTOM STRUCTURE REQUESTED:
The user has specifically guided the AI to format this answer in the following structure:
"{custom_instructions}"

MANDATORY INSTRUCTIONS:
- You MUST strictly follow the user's requested structure, headings, and presentation style rather than default templates.
- Do NOT output "DIRECT ANSWER" or standard rigid headers unless requested by the user.
- Ensure all legal positions remain rigorously grounded in Indian law, statutes, and citations.
- Conclude with a brief standard legal disclaimer."""

    else:
        # Default standard structure
        return """Always structure your response EXACTLY like this:
DIRECT ANSWER:
[Clear, direct explanation. Format key legal terms and act names cleanly without extraneous asterisks or markdown clutter.]

LEGAL BASIS:
[Relevant sections, statutory acts, and constitutional provisions in Indian law]

BINDING PRECEDENTS:
[Relevant Supreme Court or High Court landmark citations if applicable, formatted as: Case Name, Citation – Brief principle. Do NOT add unnecessary asterisks or stray symbols, or write "No direct precedent required"]

ACTIONABLE INSIGHT:
[Practical next steps, procedural precautions, limitation periods, or warnings]

DISCLAIMER:
This is for informational purposes only. Please consult a qualified advocate for legal advice."""


@router.get("/memory", response_model=LegalAidMemoryResponse)
def get_legal_aid_memory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve saved structure and formatting memory for AI Legal Aid."""
    mem = db.query(LegalAidMemory).filter(LegalAidMemory.user_id == current_user.id).first()
    if not mem:
        return LegalAidMemoryResponse(
            structure_mode="standard",
            structure_title="Standard Judicial",
            custom_instructions=None,
            updated_at=None,
        )
    return LegalAidMemoryResponse(
        structure_mode=mem.structure_mode,
        structure_title=mem.structure_title or STRUCTURE_TITLES.get(mem.structure_mode, "Custom Guided"),
        custom_instructions=mem.custom_instructions,
        updated_at=mem.updated_at,
    )


@router.post("/memory", response_model=LegalAidMemoryResponse)
def save_legal_aid_memory(
    req: LegalAidMemoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save or update user's preferred output structure in memory."""
    mem = db.query(LegalAidMemory).filter(LegalAidMemory.user_id == current_user.id).first()
    if not mem:
        mem = LegalAidMemory(user_id=current_user.id)
        db.add(mem)

    mem.structure_mode = req.structure_mode
    mem.structure_title = req.structure_title or STRUCTURE_TITLES.get(req.structure_mode, "Custom Guided")
    mem.custom_instructions = req.custom_instructions
    db.commit()
    db.refresh(mem)
    return LegalAidMemoryResponse(
        structure_mode=mem.structure_mode,
        structure_title=mem.structure_title,
        custom_instructions=mem.custom_instructions,
        updated_at=mem.updated_at,
    )


@router.delete("/memory")
def reset_legal_aid_memory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reset structure memory back to standard default."""
    mem = db.query(LegalAidMemory).filter(LegalAidMemory.user_id == current_user.id).first()
    if mem:
        db.delete(mem)
        db.commit()
    return {"status": "reset", "structure_mode": "standard", "structure_title": "Standard Judicial"}


# Real, distinct steps this flow actually performs, in the order they run --
# collapsed from a proposed 5-stage list down to 4 because there is no
# separable "cross-referencing" step distinct from retrieval in this code;
# an honest 4-stage trace beats a padded fake 5-stage one.
async def ask_legal_question_stream(
    question: str,
    n_results: int,
    db: Session,
    current_user: User,
    structure_mode: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    save_to_memory: bool = False,
):
    """Mirrors citation_verifier.verify_filing_stream's shape: one {"type": "stage",
    stage, status} event per real transition, a single terminal {"type": "done", ...}
    event carrying today's /ask response body, or {"type": "error", message} on failure."""
    try:
        # 1. Resolve user formatting memory and structure guidance
        saved_memory = db.query(LegalAidMemory).filter(LegalAidMemory.user_id == current_user.id).first()
        detected_mode, detected_guidance = detect_structure_from_query(question)

        effective_mode = structure_mode or detected_mode or (saved_memory.structure_mode if saved_memory else "standard")
        effective_custom = custom_instructions or detected_guidance or (saved_memory.custom_instructions if saved_memory else None)

        if save_to_memory:
            if not saved_memory:
                saved_memory = LegalAidMemory(user_id=current_user.id)
                db.add(saved_memory)
            saved_memory.structure_mode = effective_mode
            saved_memory.structure_title = STRUCTURE_TITLES.get(effective_mode, "Custom Guided")
            saved_memory.custom_instructions = effective_custom
            db.commit()
            db.refresh(saved_memory)

        structure_prompt_contract = build_structure_prompt_instructions(effective_mode, effective_custom)
        effective_title = STRUCTURE_TITLES.get(effective_mode, "Custom Guided")

        yield {"type": "stage", "stage": "parsing_query", "status": "started"}
        non_legal = is_non_legal_query(question)
        substance = False if non_legal else is_substance_or_extreme_query(question)
        unlawful = False if (non_legal or substance) else is_unlawful_query(question)
        yield {"type": "stage", "stage": "parsing_query", "status": "done"}

        if non_legal or substance or unlawful:
            skip_reason = "Scope rule matched — answered directly, no retrieval or generation needed"
            for stage in ("retrieving_sources", "generating_answer", "attaching_sources"):
                yield {"type": "stage", "stage": stage, "status": "skipped", "reason": skip_reason}
            if non_legal:
                payload = {"answer": NON_LEGAL_ANSWER, "requires_upgrade": False, "upgrade_tier": None}
            elif substance:
                payload = {
                    "answer": SUBSTANCE_OR_EXTREME_UPGRADE_ANSWER,
                    "requires_upgrade": True,
                    "upgrade_tier": "LexSetu Advocate Pro / Criminal Defense",
                }
            else:
                payload = {
                    "answer": UNLAWFUL_UPGRADE_ANSWER,
                    "requires_upgrade": True,
                    "upgrade_tier": "LexSetu Advocate Pro / Enterprise",
                }
            yield {
                "type": "done",
                "question": question,
                "sources": [],
                "applied_structure_mode": "standard",
                "applied_structure_title": "Standard Judicial",
                "memory_active": bool(saved_memory),
                "custom_instructions": None,
                **payload
            }
            return

        yield {"type": "stage", "stage": "retrieving_sources", "status": "started"}
        results = search_drafts(question, n_results=n_results)
        kanoon_results = scrape_indian_kanoon(question)

        context_parts = []
        for r in results:
            context_parts.append(
                f"Reference: {r['metadata']['filename']} | Category: {r['metadata']['category']}\n{r['text']}"
            )
        for k in kanoon_results:
            context_parts.append(
                f"Case Title: {k['title']}\nSnippet: {k['snippet']}\nLink: {k['link']}"
            )
        context = "\n\n---\n\n".join(context_parts) if context_parts else ""
        yield {"type": "stage", "stage": "retrieving_sources", "status": "done"}

        user_message = f"""Legal Question: {question}

{"Relevant Legal References:" + chr(10) + context if context else "Answer based on your knowledge of Indian law."}"""

        yield {"type": "stage", "stage": "generating_answer", "status": "started"}
        system_prompt = f"""You are LexSetu, an authoritative Indian legal aid intelligence assistant.
You provide clear, accurate, and actionable legal guidance based on Indian statutory law and jurisprudence.

CORE SCOPE & OPERATING POLICIES:

1. STRICTLY LEGAL QUERIES ONLY (NO CODING / NO NON-LEGAL TOPICS):
You exclusively answer questions on Indian law, statutes, court procedures, contract clauses, and judicial precedents.
You MUST NEVER write programming code (such as Python, JavaScript, HTML, C++, etc.), generate software scripts, debug software, or answer non-legal general questions (recipes, poems, stories, homework math, tech support).
If the user's question asks to write code, develop software, or covers non-legal general subjects, you MUST refuse immediately. Your DIRECT ANSWER must state:
"LexSetu is exclusively an Indian legal intelligence platform. We only reply to legal questions, statutory research inquiries, and court procedural matters. We do not generate programming code, software scripts, or non-legal general technical solutions."
In your ACTIONABLE INSIGHT, instruct them to ask a legal question or consult standard programming tools.

2. ILLICIT SUBSTANCES, WEED, ETHICALLY SENSITIVE CONDUCT & CRIMINAL EXPOSURE:
If the user's question involves illicit substances (e.g. weed, cannabis, ganja, drugs, narcotics), sensitive personal penal conduct, or asking for assistance/tricks to commit crimes, evade police, forge documents, or tamper with evidence:
You MUST NOT answer the question or provide instructions on this standard tier.
Your DIRECT ANSWER must begin with:
"Your current plan does not allow answering this question. Inquiries involving illicit substances, sensitive ethical conduct, or active personal penal liabilities cannot be addressed under the standard AI Legal Aid tier. Please upgrade your plan to LexSetu Advocate Pro to access privileged, confidential advocate consultation under Section 126 Evidence Act / Section 132 BSA."
Your ACTIONABLE INSIGHT must explicitly tell the user:
"Please upgrade your plan to the LexSetu Advocate Pro tier to consult with an empanelled Senior Criminal Defense Advocate under statutory advocate-client privilege."

3. OUTPUT STRUCTURE CONTRACT:
{structure_prompt_contract}

Formatting Rules:
- Present legal holdings and statutory citations cleanly using standard legal formatting.
- Avoid gratuitous markdown signs, repeated asterisks, or raw formatting artifacts.
- Be precise, authoritative, empathetic, and clear."""

        answer = call_llm(system_prompt, user_message)
        yield {"type": "stage", "stage": "generating_answer", "status": "done"}

        requires_upgrade = (
            "Advocate Pro" in answer or
            ("upgrade" in answer.lower() and "plan" in answer.lower()) or
            "plan does not allow" in answer.lower() or
            "does not allow answering" in answer.lower()
        )

        yield {"type": "stage", "stage": "attaching_sources", "status": "started"}
        try:
            db.add(QueryLog(
                user_id=current_user.id,
                query_type="legal_aid",
                encrypted_query=encrypt(question),
            ))
            db.commit()
        except Exception:
            pass

        sources = [
            {
                "filename": r["metadata"]["filename"],
                "category": r["metadata"]["category"],
                "score": round(r["score"], 3),
            }
            for r in results
        ]
        yield {"type": "stage", "stage": "attaching_sources", "status": "done"}

        yield {
            "type": "done",
            "question": question,
            "answer": answer,
            "sources": sources,
            "requires_upgrade": requires_upgrade,
            "upgrade_tier": "LexSetu Advocate Pro / Criminal Defense" if requires_upgrade else None,
            "applied_structure_mode": effective_mode,
            "applied_structure_title": effective_title,
            "memory_active": bool(saved_memory),
            "custom_instructions": effective_custom,
        }
    except Exception as e:
        print(f"[LegalAid] Unhandled error: {e}")
        yield {"type": "error", "message": "Legal aid request failed. Please try again."}


@router.post("/ask")
async def ask_legal_aid(
    req: LegalAidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    async def event_gen():
        async for event in ask_legal_question_stream(
            question=req.question,
            n_results=req.n_results,
            db=db,
            current_user=current_user,
            structure_mode=getattr(req, "structure_mode", None),
            custom_instructions=getattr(req, "custom_instructions", None),
            save_to_memory=getattr(req, "save_to_memory", False),
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


class LegalAidExportRequest(BaseModel):
    question: str
    answer: str
    sources: Optional[List[Dict[str, Any]]] = []


@router.post("/export-pdf")
def export_legal_aid_pdf(
    req: LegalAidExportRequest,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """Generates and downloads a structured formal Legal Advisory & Research Opinion PDF."""
    try:
        user_display = (current_user.full_name if current_user and current_user.full_name else "Advocate / Counsel")
        pdf_bytes = generate_legal_aid_pdf(
            question=req.question,
            answer=req.answer,
            sources=req.sources,
            user_name=user_display
        )
        safe_slug = re.sub(r"[^a-zA-Z0-9]+", "-", req.question.strip()[:35]).strip("-").lower()
        if not safe_slug:
            safe_slug = "opinion"
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=lexsetu-legal-opinion-{safe_slug}.pdf",
                "Content-Length": str(len(pdf_bytes)),
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as e:
        print(f"[LegalAid] PDF export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


