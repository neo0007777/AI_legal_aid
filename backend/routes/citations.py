import csv
import io
import json
import time
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models.database import User, get_db
from models.schemas import FlagCorrectionRequest, RenderLanguageRequest
from services.citation_verifier import verify_filing_stream, render_report_in_language
from services.judgment_search import get_coverage_stats, get_coverage_banner
from utils.auth import get_current_user
from utils.document_loader import load_pdf_bytes

router = APIRouter()


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
                _REPORT_STORE[report_id] = {"report": event["report"], "filing_text": text, "ts": time.time()}
                event = {**event, "report_id": report_id}
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _get_entry(report_id: str) -> dict:
    entry = _REPORT_STORE.get(report_id)
    if not entry or (time.time() - entry["ts"]) > _REPORT_TTL_SECONDS:
        raise HTTPException(status_code=404, detail="Report not found or expired. Re-run verify-filing.")
    return entry


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
    if body.language not in ("hindi", "hinglish"):
        raise HTTPException(status_code=400, detail="language must be 'hindi' or 'hinglish'.")
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
def export_pdf(report_id: str, current_user: User = Depends(get_current_user)):
    entry = _get_entry(report_id)
    report = entry["report"]
    filing_text = entry.get("filing_text", "")
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.write(10, _pdf_safe("Citation Integrity Report") + "\n")
    pdf.set_font("Helvetica", "", 9)
    pdf.write(6, _pdf_safe(report.get("coverage_banner", "")) + "\n")
    summary = report.get("summary", {})
    summary_line = (
        f"Verified: {summary.get('verified', 0)}  |  "
        f"Partial Match: {summary.get('partial_match', 0)}  |  "
        f"Mismatch: {summary.get('mismatch', 0)}  |  "
        f"Fabrication: {summary.get('possible_fabrication', 0)}  |  "
        f"Unverified: {summary.get('unverified', 0)}"
    )
    pdf.write(6, _pdf_safe(summary_line) + "\n\n")

    if filing_text:
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(7, _pdf_safe("Full Filing Text") + "\n")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(60, 40, 20)
        pdf.write(5, _pdf_safe(filing_text[:10000]) + "\n\n")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(7, _pdf_safe("Citations Found in This Filing") + "\n\n")

    for c in report["citations"]:
        case = c.get("matched_case") or (c.get("citation_identity") or {}).get("matched_case") or {}
        case_name = case.get("case_name") or c.get("case_name", "")
        cit_str = c.get("citation_string") or ""
        pdf.set_font("Helvetica", "B", 10)
        pdf.write(6, _pdf_safe(f"{case_name} {cit_str}".strip()) + "\n")
        pdf.set_font("Helvetica", "", 9)
        id_status = (c.get("citation_identity") or {}).get("status", "N/A")
        prop_status = (c.get("proposition_verification") or {}).get("status", "N/A")
        pdf.write(5, _pdf_safe(
            f"Court: {case.get('court', 'N/A')}   Date: {case.get('date', 'N/A')}   "
            f"Status: {c.get('status', '')}   [Identity: {id_status}, Proposition: {prop_status}]"
        ) + "\n")

        if c.get("adjusted_from_correction"):
            meta = c.get("correction_meta") or {}
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(109, 40, 217)
            footnote = f"* Adjusted from prior human correction"
            if meta.get("system_output"):
                footnote += f" (originally: {meta['system_output']})"
            if meta.get("note"):
                footnote += f' - "{meta["note"]}"'
            pdf.write(4, _pdf_safe(footnote) + "\n")
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
