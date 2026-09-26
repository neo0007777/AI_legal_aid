import csv
import io
import json
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models.database import User, get_db
from models.schemas import FlagCorrectionRequest, RenderLanguageRequest
from services.citation_verifier import verify_filing_stream, render_report_in_language, _RENDER_LANGUAGE_INSTRUCTIONS
from services.judgment_search import get_coverage_stats, get_coverage_banner
from services.pdf_labels import get_labels, get_status_label, PDF_FONTS
from utils.auth import get_current_user
from utils.document_loader import load_pdf_bytes

router = APIRouter()

_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")


@router.get("/coverage")
def coverage():
    """Real, live corpus coverage -- the frontend shows this wherever a user starts
    a verification (UX Consistency Pass item 2), never a hardcoded number."""
    stats = get_coverage_stats()
    return {"banner": get_coverage_banner(), **stats}

# In-memory report store keyed by report_id, for the export endpoints. Hackathon-scope:
# not persisted, not shared across processes -- fine for a single-worker dev/demo deploy.
_REPORT_STORE = {}
_REPORT_TTL_SECONDS = 3600


def _extract_filing_text(filename: str, raw: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return load_pdf_bytes(raw)
    if ext in ("txt", "text"):
        return raw.decode("utf-8", errors="ignore")
    raise HTTPException(status_code=400, detail="Only PDF or plain text (.txt) filings are supported.")


@router.post("/verify-filing")
async def verify_filing(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a filing (PDF or .txt), extract every citation, verify each one against
    the indexed judgment corpus in parallel, and stream results as an SSE event per
    citation as it completes -- not one batched response after the slowest check."""
    # S3 Task 4: entailment is pinned to Groq's gpt-oss-120b by deliberate S2 design
    # (accuracy-critical, no local fallback) -- local-only mode fails this honestly
    # and immediately rather than silently degrading the verification guarantee.
    if request.headers.get("x-local-only", "").lower() == "true":
        raise HTTPException(
            status_code=400,
            detail="Citation verification requires cloud LLM access (Groq) for the entailment check and is unavailable in local-only mode.",
        )
    raw = await file.read()
    text = _extract_filing_text(file.filename or "upload", raw)

    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Could not extract readable text from the uploaded filing.")

    report_id = str(uuid.uuid4())

    async def event_gen():
        async for event in verify_filing_stream(text):
            if event["type"] == "done":
                _persist_report(report_id, event["report"], text, getattr(current_user, "id", None))
                event = {**event, "report_id": report_id}
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


from datetime import datetime, timedelta

def _persist_report(report_id: str, report: dict, filing_text: str, user_id: str = None):
    _REPORT_STORE[report_id] = {"report": report, "filing_text": filing_text, "ts": time.time()}
    try:
        from models.database import SessionLocal, VerificationReport
        db = SessionLocal()
        try:
            expires_at = datetime.utcnow() + timedelta(days=7)
            rec = VerificationReport(
                id=report_id,
                user_id=user_id,
                report_json=json.dumps(report),
                filing_text=filing_text,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
            )
            db.merge(rec)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[Citations] Report persistence note: {e}")


def _get_entry(report_id: str) -> dict:
    entry = _REPORT_STORE.get(report_id)
    if entry and (time.time() - entry["ts"]) <= _REPORT_TTL_SECONDS:
        return entry

    try:
        from models.database import SessionLocal, VerificationReport
        db = SessionLocal()
        try:
            row = db.query(VerificationReport).filter(VerificationReport.id == report_id).first()
            if row:
                rep_data = json.loads(row.report_json)
                entry = {"report": rep_data, "filing_text": row.filing_text or "", "ts": time.time()}
                _REPORT_STORE[report_id] = entry
                return entry
        finally:
            db.close()
    except Exception as e:
        print(f"[Citations] Database report lookup error: {e}")

    raise HTTPException(status_code=404, detail="Report not found or expired. Re-run verify-filing.")


def _get_report(report_id: str) -> dict:
    return _get_entry(report_id)["report"]


@router.post("/{result_id}/flag-correction")
def flag_correction(
    result_id: str,
    body: FlagCorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        report_id, idx_str = result_id.rsplit(":", 1)
        idx = int(idx_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid result_id format; expected '<report_id>:<citation_index>'.")

    report = _get_report(report_id)
    citations = report["citations"]
    if idx < 0 or idx >= len(citations):
        raise HTTPException(status_code=404, detail="Citation not found in this report.")

    citation = citations[idx]
    case_name = citation.get("case_name", "")
    citation_string = citation.get("citation_string", "")
    system_output = citation.get("status")

    from services import correction_memory as cm
    if body.correct_output not in cm.STATE_ORDER:
        raise HTTPException(status_code=400, detail=f"correct_output must be one of {list(cm.STATE_ORDER)}.")
    if body.correct_output == system_output:
        raise HTTPException(status_code=400, detail="correct_output must differ from the system's current verdict.")

    row = cm.create_correction(
        db, trigger_type="citation_verdict", case_name=case_name, citation_string=citation_string,
        system_output=system_output, correct_output=body.correct_output,
        flagged_by=current_user.id, note=body.note,
    )
    return {
        "id": row.id,
        "direction": row.direction,
        "status": row.status,
        "message": (
            "Applied immediately."
            if row.direction == "tighten"
            else "Submitted for review — won't change results until confirmed."
        ),
    }


@router.post("/{report_id}/render")
def render_language(report_id: str, body: RenderLanguageRequest, current_user: User = Depends(get_current_user)):
    if body.language not in _RENDER_LANGUAGE_INSTRUCTIONS:
        raise HTTPException(status_code=400, detail=f"language must be one of {list(_RENDER_LANGUAGE_INSTRUCTIONS)}.")
    report = _get_report(report_id)
    try:
        return render_report_in_language(report, body.language)
    except Exception as e:
        print(f"[Citations] render_language failed: {e}")
        raise HTTPException(status_code=503, detail="Translation service was unavailable. Please try again.")


@router.get("/export/{report_id}.csv")
def export_csv(report_id: str, current_user: User = Depends(get_current_user)):
    report = _get_report(report_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Case", "Reported Citation", "Court", "Date", "Status", "Identity Status", "Proposition Status", "Source Link"])
    for c in report["citations"]:
        case = c.get("matched_case") or (c.get("citation_identity") or {}).get("matched_case") or {}
        writer.writerow([
            case.get("case_name") or c.get("case_name", ""),
            c.get("citation_string", ""),
            case.get("court", ""),
            case.get("date", ""),
            c.get("status", ""),
            (c.get("citation_identity") or {}).get("status", ""),
            (c.get("proposition_verification") or {}).get("status", ""),
            c.get("source_link") or "",
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=citation-integrity-report-{report_id[:8]}.csv"},
    )


@router.get("/export/{report_id}.pdf")
def export_pdf(
    report_id: str,
    lang: Optional[str] = Query(None, description="Render the PDF's static labels + status words in this language (e.g. 'hindi'). Case names, citations, section numbers and the filing text itself always stay in their original form."),
    current_user: User = Depends(get_current_user),
):
    entry = _get_entry(report_id)
    report = entry["report"]
    filing_text = entry.get("filing_text", "")
    from fpdf import FPDF

    # `lang` only ever affects DISPLAY -- it's the same already-verified
    # English report, just relabeled. 'hinglish' is Roman-script already so
    # it uses the English (Helvetica-safe) label set, not a Unicode font.
    use_lang = lang if (lang and lang in _RENDER_LANGUAGE_INSTRUCTIONS and lang != "hinglish") else None
    labels = get_labels(use_lang or "en")
    font_name = PDF_FONTS.get(use_lang)

    pdf = FPDF()
    pdf.add_page()

    if font_name:
        font_path = os.path.join(_FONTS_DIR, f"{font_name}.ttf")
        pdf.add_font(font_name, "", font_path)
        pdf.set_text_shaping(True)

        def set_font(style="", size=10):
            # The embedded Noto variable fonts ship one weight -- style is
            # accepted for call-site parity but always resolves to the same face.
            pdf.set_font(font_name, "", size)

        def safe(text):
            return text  # Unicode font -- no Latin-1 fallback needed
    else:
        def set_font(style="", size=10):
            pdf.set_font("Helvetica", style, size)

        def safe(text):
            return _pdf_safe(text)

    set_font("B", 14)
    pdf.write(10, safe(labels["title"]) + "\n")
    set_font("", 9)
    pdf.write(6, safe(report.get("coverage_banner", "")) + "\n")
    summary = report.get("summary", {})
    summary_line = (
        f"{labels['summary_verified']}: {summary.get('verified', 0)}  |  "
        f"{labels['summary_partial']}: {summary.get('partial_match', 0)}  |  "
        f"{labels['summary_mismatch']}: {summary.get('mismatch', 0)}  |  "
        f"{labels['summary_fabrication']}: {summary.get('possible_fabrication', 0)}  |  "
        f"{labels['summary_unverified']}: {summary.get('unverified', 0)}"
    )
    pdf.write(6, safe(summary_line) + "\n\n")

    if filing_text:
        set_font("B", 11)
        pdf.write(7, safe(labels["full_filing_text"]) + "\n")
        set_font("", 8)
        pdf.set_text_color(60, 40, 20)
        # The user's own uploaded filing is reproduced verbatim, never
        # translated -- it's the original document being audited, not
        # LexSetu's own output.
        pdf.write(5, _pdf_safe(filing_text[:10000]) + "\n\n")
        pdf.set_text_color(0, 0, 0)
        set_font("B", 11)
        pdf.write(7, safe(labels["citations_found"]) + "\n\n")

    for c in report["citations"]:
        case = c.get("matched_case") or (c.get("citation_identity") or {}).get("matched_case") or {}
        case_name = case.get("case_name") or c.get("case_name", "")
        cit_str = c.get("citation_string") or ""
        set_font("B", 10)
        # Case name / citation string / court / date are identifiers, not
        # descriptive prose -- kept in their original English/Latin form.
        pdf.write(6, _pdf_safe(f"{case_name} {cit_str}".strip()) + "\n")
        set_font("", 9)
        id_status = (c.get("citation_identity") or {}).get("status", labels["na"])
        prop_status = (c.get("proposition_verification") or {}).get("status", labels["na"])
        status_label = get_status_label(use_lang or "en", c.get("status", ""))
        pdf.write(5, safe(
            f"{labels['court']}: {str(case.get('court') or labels['na'])}   "
            f"{labels['date']}: {str(case.get('date') or labels['na'])}   "
            f"{labels['status']}: {status_label}   [{labels['identity']}: {id_status}, {labels['proposition']}: {prop_status}]"
        ) + "\n")

        if c.get("adjusted_from_correction"):
            meta = c.get("correction_meta") or {}
            set_font("I", 8)
            pdf.set_text_color(109, 40, 217)
            footnote = labels["adjusted_note"]
            if meta.get("system_output"):
                footnote += f" ({labels['originally']}: {meta['system_output']})"
            if meta.get("note"):
                footnote += f' - "{meta["note"]}"'
            pdf.write(4, safe(footnote) + "\n")
            pdf.set_text_color(0, 0, 0)

        pdf.write(4, "\n")


    pdf_bytes = bytes(pdf.output())
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=citation-integrity-report-{report_id[:8]}.pdf"},
    )



@router.delete("/{report_id}/purge")
def purge_report(report_id: str):
    """Purge in-memory report from _REPORT_STORE."""
    _REPORT_STORE.pop(report_id, None)
    return {"status": "purged", "report_id": report_id}


def _pdf_safe(text: str) -> str:
    # Core Helvetica is strict Latin-1 (not Windows-1252), which excludes the en/em
    # dashes used elsewhere in this report (e.g. paragraph ranges, the coverage
    # banner's year range) -- normalize those first so they render as "-" instead of
    # the encode-error fallback "?".
    text = (text or "").replace("–", "-").replace("—", "-")
    return text.encode("latin-1", errors="replace").decode("latin-1")
