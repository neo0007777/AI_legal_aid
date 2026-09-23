import csv
import io
import json
import time
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse

from models.database import User
from services.citation_verifier import verify_filing_stream
from services.judgment_search import get_coverage_stats, get_coverage_banner
from utils.auth import get_current_user
from utils.document_loader import load_pdf_bytes

router = APIRouter()


@router.get("/coverage")
def coverage(current_user: User = Depends(get_current_user)):
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
                _REPORT_STORE[report_id] = {"report": event["report"], "ts": time.time()}
                event = {**event, "report_id": report_id}
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _get_report(report_id: str) -> dict:
    entry = _REPORT_STORE.get(report_id)
    if not entry or (time.time() - entry["ts"]) > _REPORT_TTL_SECONDS:
        raise HTTPException(status_code=404, detail="Report not found or expired. Re-run verify-filing.")
    return entry["report"]


@router.get("/export/{report_id}.csv")
def export_csv(report_id: str, current_user: User = Depends(get_current_user)):
    report = _get_report(report_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Case", "Court", "Date", "Paragraph", "Status", "Source Link"])
    for c in report["citations"]:
        case = c.get("matched_case") or {}
        writer.writerow([
            case.get("case_name") or c.get("case_name", ""),
            case.get("court", ""),
            case.get("date", ""),
            c.get("paragraph_display") or "",
            c.get("status", ""),
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
    report = _get_report(report_id)
    from fpdf import FPDF

    # Uses write() throughout, not multi_cell/cell: this fpdf2 version's multi_cell
    # intermittently raises "Not enough horizontal space" on some strings for reasons
    # that didn't reproduce with write() in testing -- write() with embedded newlines
    # covers the same layout need (wrapping title/case blocks) without the bug.
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.write(10, _pdf_safe("Citation Integrity Report") + "\n")
    pdf.set_font("Helvetica", "", 9)
    pdf.write(6, _pdf_safe(report.get("coverage_banner", "")) + "\n")
    summary = report.get("summary", {})
    pdf.write(6, _pdf_safe(
        f"Verified: {summary.get('verified', 0)}  |  Mismatch: {summary.get('mismatch', 0)}  |  "
        f"Not found in indexed corpus: {summary.get('not_found', 0)}"
    ) + "\n\n")

    for c in report["citations"]:
        case = c.get("matched_case") or {}
        case_name = case.get("case_name") or c.get("case_name", "")
        pdf.set_font("Helvetica", "B", 10)
        pdf.write(6, _pdf_safe(case_name) + "\n")
        pdf.set_font("Helvetica", "", 9)
        pdf.write(5, _pdf_safe(
            f"Court: {case.get('court', 'N/A')}   Date: {case.get('date', 'N/A')}   "
            f"Paragraph: {c.get('paragraph_display') or 'N/A'}   Status: {c.get('status', '')}"
        ) + "\n\n")

    pdf_bytes = bytes(pdf.output())
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=citation-integrity-report-{report_id[:8]}.pdf"},
    )


def _pdf_safe(text: str) -> str:
    # Core Helvetica is strict Latin-1 (not Windows-1252), which excludes the en/em
    # dashes used elsewhere in this report (e.g. paragraph ranges, the coverage
    # banner's year range) -- normalize those first so they render as "-" instead of
    # the encode-error fallback "?".
    text = (text or "").replace("–", "-").replace("—", "-")
    return text.encode("latin-1", errors="replace").decode("latin-1")
