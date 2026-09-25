import re
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models.database import get_db, User, QueryLog
from models.schemas import LegalAidRequest, LegalAidResponse, SearchSource
from services.rag import search_drafts
from services.llm import call_llm
from utils.auth import get_current_user
from utils.encryption import encrypt
from services.scraper import scrape_indian_kanoon

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


@router.post("/ask", response_model=LegalAidResponse)
def ask_legal_aid(
    req: LegalAidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Scope Rule 1: Strictly legal queries only — reject programming code / software requests
    if is_non_legal_query(req.question):
        return LegalAidResponse(
            question=req.question,
            answer=NON_LEGAL_ANSWER,
            sources=[],
            requires_upgrade=False,
        )

    # Scope Rule 2: Illicit substances, weed, narcotics, extreme personal penal matters — upgrade plan required
    if is_substance_or_extreme_query(req.question):
        return LegalAidResponse(
            question=req.question,
            answer=SUBSTANCE_OR_EXTREME_UPGRADE_ANSWER,
            sources=[],
            requires_upgrade=True,
            upgrade_tier="LexSetu Advocate Pro / Criminal Defense",
        )

    # Scope Rule 3: Active crime facilitation, bribery, forgery, evasion — upgrade plan required
    if is_unlawful_query(req.question):
        return LegalAidResponse(
            question=req.question,
            answer=UNLAWFUL_UPGRADE_ANSWER,
            sources=[],
            requires_upgrade=True,
            upgrade_tier="LexSetu Advocate Pro / Enterprise",
        )

    try:
        results = search_drafts(req.question, n_results=req.n_results)
        kanoon_results = scrape_indian_kanoon(req.question)

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

        system_prompt = """You are LexSetu, an authoritative Indian legal aid intelligence assistant.
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

Always structure your response EXACTLY like this:
DIRECT ANSWER:
[Clear, direct explanation. Format key legal terms and act names cleanly without extraneous asterisks or markdown clutter.]

LEGAL BASIS:
[Relevant sections, statutory acts, and constitutional provisions in Indian law]

BINDING PRECEDENTS:
[Relevant Supreme Court or High Court landmark citations if applicable, formatted as: Case Name, Citation – Brief principle. Do NOT add unnecessary asterisks or stray symbols, or write "No direct precedent required"]

ACTIONABLE INSIGHT:
[Practical next steps, procedural precautions, limitation periods, or warnings]

DISCLAIMER:
This is for informational purposes only. Please consult a qualified advocate for legal advice.

Formatting Rules:
- Present legal holdings and statutory citations cleanly using standard legal formatting.
- Avoid gratuitous markdown signs, repeated asterisks, or raw formatting artifacts.
- Be precise, authoritative, empathetic, and clear."""

        user_message = f"""Legal Question: {req.question}

{"Relevant Legal References:" + chr(10) + context if context else "Answer based on your knowledge of Indian law."}"""

        answer = call_llm(system_prompt, user_message)
        requires_upgrade = (
            "Advocate Pro" in answer or
            ("upgrade" in answer.lower() and "plan" in answer.lower()) or
            "plan does not allow" in answer.lower() or
            "does not allow answering" in answer.lower()
        )

        try:
            db.add(QueryLog(
                user_id=current_user.id,
                query_type="legal_aid",
                encrypted_query=encrypt(req.question),
            ))
            db.commit()
        except Exception:
            pass

        return LegalAidResponse(
            question=req.question,
            answer=answer,
            sources=[
                SearchSource(
                    filename=r["metadata"]["filename"],
                    category=r["metadata"]["category"],
                    score=round(r["score"], 3),
                )
                for r in results
            ],
            requires_upgrade=requires_upgrade,
            upgrade_tier="LexSetu Advocate Pro / Criminal Defense" if requires_upgrade else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[LegalAid] Unhandled error: {e}")
        raise HTTPException(status_code=500, detail="Legal aid request failed. Please try again.")

