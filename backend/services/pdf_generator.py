"""
LexSetu Legal PDF Generation Engine
Generates court-grade, beautifully structured, publication-quality legal PDFs using fpdf2.

Supports:
1. AI Legal Aid: Formal Legal Advisory & Statutory Opinion
2. Case Finder: Judicial Precedent Research Brief & Case Law Dossier
3. Draft Assistant: Standard Indian Court Pleading (A4 format with court margins)
"""

import io
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def clean_pdf_text(text: str) -> str:
    """Sanitizes text to be completely compatible with standard PDF Helvetica encoding."""
    if not text:
        return ""
    replacements = {
        "—": "-",
        "–": "-",
        "―": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "•": "*",
        "▪": "*",
        "■": "*",
        "━": "=",
        "─": "-",
        "₹": "Rs. ",
        "…": "...",
        "→": "->",
        "←": "<-",
        "⇒": "=>",
        "§": "Sec. ",
        "©": "(c)",
        "®": "(r)",
        "™": "(tm)",
        "\u202F": " ",
        "\u00A0": " ",
        "\u200B": "",
        "\u200E": "",
        "\u200F": "",
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    
    # Strip gratuitous markdown asterisks or hashes
    text = re.sub(r"\*{2,3}(.*?)\*{2,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    
    # Ensure all chars fall into Latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


class BaseLexSetuPDF(FPDF):
    """Base PDF with LexSetu header and statutory privilege footer."""
    def __init__(self, doc_category: str = "LEGAL INTELLIGENCE DOSSIER", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.doc_category = doc_category
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() == 1:
            # Top decorative bar
            self.set_fill_color(99, 18, 14) # #63120e burgundy
            self.rect(0, 0, 210, 5, style="F")
            return

        # Running header for pages 2+
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(130, 130, 130)
        self.cell(100, 7, clean_pdf_text(f"LEXSETU | {self.doc_category}"), align="L")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 7, datetime.now().strftime("%d %b %Y"), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, 17, 210 - self.r_margin, 17)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(140, 140, 140)
        self.cell(
            120, 8,
            clean_pdf_text("Privileged & Confidential | Section 126 IEA / Section 132 BSA | LexSetu"),
            align="L"
        )
        self.cell(
            0, 8,
            clean_pdf_text(f"Page {self.page_no()} of {{nb}}"),
            align="R",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )


# ═══════════════════════════════════════════════════════
# 1. AI LEGAL AID PDF GENERATION
# ═══════════════════════════════════════════════════════

def generate_legal_aid_pdf(
    question: str,
    answer: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    user_name: Optional[str] = "Counsel / Litigant"
) -> bytes:
    """Generates a structured legal advisory PDF from an AI Legal Aid response."""
    pdf = BaseLexSetuPDF(doc_category="LEGAL AID & ADVISORY OPINION")
    pdf.alias_nb_pages()
    pdf.set_margins(15, 18, 15)
    pdf.add_page()

    # 1. Header & Title Block
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(99, 18, 14) # Brand burgundy
    pdf.cell(pdf.epw, 9, clean_pdf_text("LexSetu Legal Intelligence"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(pdf.epw, 6, clean_pdf_text("FORMAL LEGAL ADVISORY & STATUTORY RESEARCH OPINION"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    # Metadata Line
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(110, 110, 110)
    date_str = datetime.now().strftime("%B %d, %Y - %I:%M %p IST")
    meta_line = f"Date of Issue: {date_str}   |   Recipient: {user_name}   |   Domain: Indian Law & Jurisprudence"
    pdf.cell(pdf.epw, 5, clean_pdf_text(meta_line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Gold Accent Line
    pdf.set_draw_color(217, 164, 111) # #dfa46f
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, 210 - pdf.r_margin, pdf.get_y() + 2)
    pdf.ln(5)

    # 2. Query / Matter Presented Callout Box
    pdf.set_fill_color(249, 238, 220) # #f9eedc
    pdf.set_draw_color(217, 164, 111)
    pdf.set_line_width(0.4)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(99, 18, 14)
    pdf.cell(pdf.epw, 6, clean_pdf_text("SUBJECT MATTER / INQUIRY PRESENTED:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", "I", 9.5)
    pdf.set_text_color(30, 30, 30)
    cleaned_q = clean_pdf_text(question.strip())
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5.5, cleaned_q)
    pdf.ln(3)

    # 3. Parse and Render Answer Sections
    section_patterns = [
        ("DIRECT ANSWER", "I. DIRECT LEGAL OPINION & SUMMARY", (99, 18, 14)),
        ("LEGAL BASIS", "II. STATUTORY GROUNDS & LEGAL PROVISIONS", (31, 78, 120)),
        ("BINDING PRECEDENTS", "III. JUDICIAL PRECEDENTS & AUTHORITIES CITED", (140, 80, 10)),
        ("ACTIONABLE INSIGHT", "IV. ACTIONABLE COUNSEL & STRATEGIC STEPS", (40, 120, 60)),
        ("ACTIONABLE COUNSEL & STRATEGIC STEPS", "IV. ACTIONABLE COUNSEL & STRATEGIC STEPS", (40, 120, 60)),
        ("DISCLAIMER", "V. STATUTORY NOTICE & DISCLAIMER", (120, 120, 120)),
    ]

    pattern = r"(?:^|\n)(?:#+\s*)?(?:\*\*)?(DIRECT ANSWER|LEGAL BASIS|BINDING PRECEDENTS|ACTIONABLE INSIGHT|ACTIONABLE COUNSEL & STRATEGIC STEPS|DISCLAIMER):?(?:\*\*)?"
    parts = re.split(pattern, answer, flags=re.IGNORECASE)

    parsed_sections = {}
    if len(parts) > 1:
        for i in range(1, len(parts), 2):
            sec_name = parts[i].upper().strip()
            sec_body = parts[i+1].strip() if i+1 < len(parts) else ""
            parsed_sections[sec_name] = sec_body
    else:
        parsed_sections["DIRECT ANSWER"] = answer.strip()

    for raw_key, display_heading, color_rgb in section_patterns:
        content = parsed_sections.get(raw_key) or parsed_sections.get(raw_key.replace(":", ""))
        if not content:
            continue

        pdf.ln(4)
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(245, 245, 247)
        pdf.set_text_color(*color_rgb)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6.5, clean_pdf_text(f"  {display_heading}"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(35, 35, 35)
        
        lines = content.split("\n")
        for line in lines:
            line_str = line.strip()
            if not line_str:
                pdf.ln(2)
                continue
            
            cleaned_line = clean_pdf_text(line_str)
            pdf.set_x(pdf.l_margin)
            if cleaned_line.startswith("*") or cleaned_line.startswith("-"):
                bullet_text = cleaned_line.lstrip("*- ").strip()
                pdf.multi_cell(pdf.epw, 5.2, f"  *  {bullet_text}")
            elif re.match(r"^\d+\.\s+", cleaned_line):
                pdf.multi_cell(pdf.epw, 5.2, f"  {cleaned_line}")
            else:
                pdf.multi_cell(pdf.epw, 5.2, cleaned_line)

    # 4. Source Citations & References Table (if provided)
    if sources and len(sources) > 0:
        pdf.ln(5)
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(245, 245, 247)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6.5, clean_pdf_text("  VI. STATUTORY SOURCES & DATABASE CITATIONS"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(230, 230, 235)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(50, 50, 50)
        col1 = pdf.epw * 0.55
        col2 = pdf.epw * 0.25
        col3 = pdf.epw * 0.20
        pdf.cell(col1, 6, "Reference Document / Statute", border=1, fill=True)
        pdf.cell(col2, 6, "Legal Category", border=1, fill=True)
        pdf.cell(col3, 6, "Relevance Score", border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", "", 8)
        for s in sources[:6]:
            fname = s.get("filename", "") if isinstance(s, dict) else getattr(s, "filename", "")
            cat = s.get("category", "") if isinstance(s, dict) else getattr(s, "category", "")
            score = s.get("score", 0.0) if isinstance(s, dict) else getattr(s, "score", 0.0)
            score_str = f"{int(score * 100)}%" if score else "High"
            
            pdf.set_x(pdf.l_margin)
            pdf.cell(col1, 5.5, clean_pdf_text(fname[:55]), border=1)
            pdf.cell(col2, 5.5, clean_pdf_text(cat.capitalize()), border=1)
            pdf.cell(col3, 5.5, clean_pdf_text(score_str), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 5. Sign-off Stamp
    pdf.ln(6)
    pdf.set_x(pdf.l_margin)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(2.5)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(130, 130, 130)
    pdf.multi_cell(
        pdf.epw, 4,
        clean_pdf_text(
            "Certified Legal Research Output generated by LexSetu Intelligence System. "
            "Pursuant to Bar Council of India guidelines, this document provides analytical legal information and does not establish a formal advocate-client relationship. "
            "For court filings or litigation strategy, please consult an advocate."
        )
    )

    return bytes(pdf.output())


# ═══════════════════════════════════════════════════════
# 2. CASE FINDER RESEARCH DOSSIER PDF GENERATION
# ═══════════════════════════════════════════════════════

def generate_case_finder_pdf(
    query: str,
    ai_synthesis: str,
    live_cases: Optional[List[Dict[str, Any]]] = None,
    local_sources: Optional[List[Dict[str, Any]]] = None,
) -> bytes:
    """Generates an exhaustive Case Law Research Brief & Judicial Precedent Dossier."""
    pdf = BaseLexSetuPDF(doc_category="CASE LAW RESEARCH BRIEF")
    pdf.alias_nb_pages()
    pdf.set_margins(15, 18, 15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(99, 18, 14)
    pdf.cell(pdf.epw, 9, clean_pdf_text("LexSetu Case Law Intelligence"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(pdf.epw, 6, clean_pdf_text("JUDICIAL PRECEDENT & LANDMARK CASE BRIEFING"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Metadata
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(110, 110, 110)
    date_str = datetime.now().strftime("%B %d, %Y - %I:%M %p IST")
    pdf.cell(pdf.epw, 5, clean_pdf_text(f"Generated: {date_str}   |   Jurisdiction: Supreme Court & High Courts of India"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Accent line
    pdf.set_draw_color(217, 164, 111)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, 210 - pdf.r_margin, pdf.get_y() + 2)
    pdf.ln(5)

    # Research Query Callout
    pdf.set_fill_color(249, 238, 220)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(99, 18, 14)
    pdf.cell(pdf.epw, 6, clean_pdf_text("RESEARCH PROPOSITION / SEARCH QUERY:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5.5, clean_pdf_text(f'"{query.strip()}"'))
    pdf.ln(3)

    # Section 1: AI Judicial Synthesis
    if ai_synthesis and ai_synthesis.strip():
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(245, 245, 247)
        pdf.set_text_color(99, 18, 14)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6.5, clean_pdf_text("  I. JUDICIAL SYNTHESIS & CORE DOCTRINES"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(35, 35, 35)
        for line in ai_synthesis.split("\n"):
            l = line.strip()
            if not l:
                pdf.ln(1.5)
                continue
            pdf.set_x(pdf.l_margin)
            if l.startswith("━") or l.startswith("="):
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_text_color(50, 50, 50)
                pdf.cell(pdf.epw, 5.5, clean_pdf_text(l.replace("━", "").strip()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(35, 35, 35)
            elif l.startswith("•") or l.startswith("*"):
                pdf.multi_cell(pdf.epw, 4.8, f"  *  {clean_pdf_text(l.lstrip('•* ').strip())}")
            else:
                pdf.multi_cell(pdf.epw, 4.8, clean_pdf_text(l))

    # Section 2: Landmark Judgments from Indian Kanoon
    cases = live_cases or []
    if cases:
        pdf.ln(5)
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(245, 245, 247)
        pdf.set_text_color(31, 78, 120)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(pdf.epw, 6.5, clean_pdf_text(f"  II. RELEVANT LANDMARK PRECEDENTS ({len(cases)} JUDGMENTS)"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)

        for i, c in enumerate(cases, 1):
            title = c.get("title", "") if isinstance(c, dict) else getattr(c, "title", "")
            source = c.get("source", "Indian Kanoon") if isinstance(c, dict) else getattr(c, "source", "Indian Kanoon")
            snippet = c.get("snippet", "") if isinstance(c, dict) else getattr(c, "snippet", "")
            link = c.get("link", "") if isinstance(c, dict) else getattr(c, "link", "")
            keywords = c.get("keywords", []) if isinstance(c, dict) else getattr(c, "keywords", [])

            pdf.set_x(pdf.l_margin)
            pdf.set_fill_color(240, 244, 250)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(20, 60, 110)
            pdf.cell(pdf.epw, 6, clean_pdf_text(f"  {i}. {title}"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "I", 7.5)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(pdf.epw, 4.5, clean_pdf_text(f"Bench/Source: {source}   |   Reference: {link[:80]}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            if snippet:
                pdf.set_x(pdf.l_margin)
                pdf.set_font("Helvetica", "", 8.5)
                pdf.set_text_color(40, 40, 40)
                pdf.multi_cell(pdf.epw, 4.5, clean_pdf_text(f"Key Extract: {snippet}"))
            
            if keywords:
                pdf.set_x(pdf.l_margin)
                pdf.set_font("Helvetica", "B", 7.5)
                pdf.set_text_color(120, 90, 40)
                kw_str = "Keywords: " + ", ".join(keywords[:6])
                pdf.cell(pdf.epw, 4, clean_pdf_text(kw_str), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            pdf.ln(2.5)

    return bytes(pdf.output())


# ═══════════════════════════════════════════════════════
# 3. DRAFT ASSISTANT COURT PLEADING PDF GENERATION
# ═══════════════════════════════════════════════════════

class CourtPleadingPDF(FPDF):
    """Court-compliant A4 PDF with 30mm left margin for ribbon/filing."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_margins(30, 25, 18)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(140, 140, 140)
            self.cell(self.epw, 6, clean_pdf_text("[ COURT PLEADING -- IN RE: LEGAL PROCEEDINGS ]"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(self.epw, 8, clean_pdf_text(f"- {self.page_no()} -"), align="C")


def generate_court_draft_pdf(
    title: str,
    draft_text: str,
    court_name: Optional[str] = None,
    case_number: Optional[str] = None,
    applicant: Optional[str] = None,
    respondent: Optional[str] = None,
) -> bytes:
    """
    Renders a standard Indian Court Pleading in A4 PDF format:
    - Formal Court Header
    - Cause Title (Parties block)
    - Pleading Body with numbered paragraphs
    - Prayer clause
    - Verification affidavit block
    - Advocate sign-off
    """
    pdf = CourtPleadingPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # 1. Court Name Header (Centered, Bold, Uppercase)
    court_title = court_name.strip() if court_name and court_name.strip() else "IN THE COURT OF THE PRINCIPAL DISTRICT & SESSIONS JUDGE"
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5.5, clean_pdf_text(court_title.upper()), align="C")
    pdf.ln(2)

    # 2. Case Number / Category
    case_no_str = case_number.strip() if case_number and case_number.strip() else "CRIMINAL / CIVIL MISC. APPLICATION NO. _______ OF 2026"
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(pdf.epw, 5.5, clean_pdf_text(case_no_str.upper()), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # 3. Cause Title / Parties Block
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(pdf.epw, 5, clean_pdf_text("IN THE MATTER OF:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    app_name = applicant.strip() if applicant and applicant.strip() else "[APPLICANT / PETITIONER NAME]"
    resp_name = respondent.strip() if respondent and respondent.strip() else "[RESPONDENT / STATE]"

    w_half = pdf.epw * 0.65
    w_role = pdf.epw * 0.35

    pdf.set_font("Helvetica", "", 9.5)
    pdf.cell(w_half, 5.5, clean_pdf_text(app_name))
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(w_role, 5.5, "... APPLICANT / PETITIONER", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(pdf.epw, 6, "VERSUS", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 9.5)
    pdf.cell(w_half, 5.5, clean_pdf_text(resp_name))
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(w_role, 5.5, "... RESPONDENT", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # 4. Heading / Application Title (Centered, Bold, Underlined)
    app_title = title.strip() if title and title.strip() else "APPLICATION UNDER RELEVANT PROVISIONS OF LAW"
    pdf.set_font("Helvetica", "BU", 10.5)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5.5, clean_pdf_text(app_title.upper()), align="C")
    pdf.ln(4)

    # 5. Respectful Submission Header
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(pdf.epw, 6, clean_pdf_text("MOST RESPECTFULLY SHOWETH:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # 6. Parse Draft Content into Pleading Paragraphs
    pdf.set_font("Helvetica", "", 10)
    paragraphs = draft_text.split("\n\n")

    in_prayer = False
    in_verification = False

    for para in paragraphs:
        p_clean = para.strip()
        if not p_clean:
            continue

        p_upper = p_clean.upper()

        if "PRAYER" in p_upper or p_upper.startswith("PRAYER:"):
            in_prayer = True
            pdf.ln(4)
            pdf.set_font("Helvetica", "BU", 10)
            pdf.cell(pdf.epw, 6, "PRAYER", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 9.5)
            sub_text = re.sub(r"^PRAYER:?\s*", "", p_clean, flags=re.IGNORECASE).strip()
            if sub_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(pdf.epw, 5.2, clean_pdf_text(sub_text))
            continue

        if "VERIFICATION" in p_upper or p_upper.startswith("VERIFICATION:"):
            in_verification = True
            pdf.ln(5)
            pdf.set_font("Helvetica", "BU", 10)
            pdf.cell(pdf.epw, 6, "VERIFICATION", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 9.5)
            sub_text = re.sub(r"^VERIFICATION:?\s*", "", p_clean, flags=re.IGNORECASE).strip()
            if sub_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(pdf.epw, 5.2, clean_pdf_text(sub_text))
            continue

        pdf.set_font("Helvetica", "", 9.5)
        cleaned_para = clean_pdf_text(p_clean)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 5.2, cleaned_para)
        pdf.ln(2)

    # 7. Verification Clause (if not already found in text)
    if not in_verification:
        pdf.ln(5)
        pdf.set_font("Helvetica", "BU", 10)
        pdf.cell(pdf.epw, 6, "VERIFICATION", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 9)
        verif_text = (
            "Verified at New Delhi on this day that the contents of the above application are true "
            "and correct to the best of my knowledge, and derived from legal records believed to be true. "
            "No part of it is false and nothing material has been concealed therefrom."
        )
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 5, clean_pdf_text(verif_text))
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.epw, 5, "DEPONENT", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 8. Advocate Sign-off Block
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 8.5)
    col_w = pdf.epw * 0.5
    pdf.cell(col_w, 4.5, "FILED BY:", align="L")
    pdf.cell(col_w, 4.5, "THROUGH", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(col_w, 4.5, "Advocate for Applicant", align="L")
    pdf.cell(col_w, 4.5, "[ADVOCATE ON RECORD]", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.cell(col_w, 4.5, "Enrollment No.: ____________", align="L")
    pdf.cell(col_w, 4.5, "Chamber / Office: _________________", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.cell(col_w, 4.5, "Date: " + datetime.now().strftime("%d.%m.%Y"), align="L")
    pdf.cell(col_w, 4.5, "New Delhi, India", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
