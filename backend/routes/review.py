from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
import json
import io
from models.review_models import (
    ReviewRequest, ReviewResponse, FixRequest, FixResponse
)
from services.review_engine import run_hybrid_review, auto_fix_draft
from pypdf import PdfReader

router = APIRouter()


@router.post("/analyze", response_model=ReviewResponse)
@router.post("", response_model=ReviewResponse)
@router.post("/", response_model=ReviewResponse)
def review_draft(req: ReviewRequest):
    """Reviews text draft using universal Qdrant RAG + LLM legal review pipeline."""
    if not req.draft.strip():
        raise HTTPException(status_code=400, detail="Draft content cannot be empty")

    try:
        posture = None
        manifest = None
        try:
            from services.legal_reasoning_engine import identify_procedural_posture
            from services.fact_manifest import build_manifest
            posture = identify_procedural_posture(req.draft)
            manifest = build_manifest(req.draft, req.document_type)
        except Exception as ctx_err:
            print(f"[ReviewRoute] Context build notice: {ctx_err}")

        return run_hybrid_review(req.draft, req.document_type, fact_manifest=manifest, procedural_posture=posture)
    except Exception as e:
        print(f"[ReviewRoute] Error in review_draft: {e}")
        raise HTTPException(status_code=500, detail=f"Review engine failed: {str(e)}")


@router.post("/file", response_model=ReviewResponse)
async def review_uploaded_file(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None)
):
    """Extracts text from uploaded PDF/DOCX/TXT/RTF file and runs universal review engine."""
    filename = file.filename.lower()
    content_bytes = await file.read()
    extracted_text = ""

    try:
        if filename.endswith(".pdf"):
            pdf_reader = PdfReader(io.BytesIO(content_bytes))
            extracted_text = "\n".join([page.extract_text() or "" for page in pdf_reader.pages])
        elif filename.endswith(".docx"):
            extracted_text = load_docx_bytes(content_bytes)
        elif filename.endswith(".rtf"):
            extracted_text = load_rtf_bytes(content_bytes)
        elif filename.endswith(".txt"):
            extracted_text = content_bytes.decode("utf-8", errors="ignore")
        else:
            extracted_text = content_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text from {file.filename}: {str(e)}")

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail=f"No readable text could be extracted from {file.filename}")

    posture = None
    manifest = None
    try:
        from services.legal_reasoning_engine import identify_procedural_posture
        from services.fact_manifest import build_manifest
        posture = identify_procedural_posture(extracted_text)
        manifest = build_manifest(extracted_text, document_type)
    except Exception as ctx_err:
        print(f"[ReviewRoute] Context build notice: {ctx_err}")

    return run_hybrid_review(extracted_text, document_type, fact_manifest=manifest, procedural_posture=posture)


@router.post("/fix", response_model=FixResponse)
def fix_draft(req: FixRequest):
    """Auto-fixes detected issues in the draft while preserving layout and correct clauses."""
    if not req.draft.strip():
        raise HTTPException(status_code=400, detail="Original draft content cannot be empty")

    try:
        posture = None
        manifest = None
        try:
            from services.legal_reasoning_engine import identify_procedural_posture
            from services.fact_manifest import build_manifest
            posture = identify_procedural_posture(req.draft)
            manifest = build_manifest(req.draft)
        except Exception as ctx_err:
            print(f"[ReviewRoute] Fix context build notice: {ctx_err}")

        return auto_fix_draft(
            draft=req.draft,
            issues=req.issues,
            missing_sections=req.missing_sections,
            missing_fields=req.missing_fields,
            fact_manifest=manifest,
            procedural_posture=posture
        )
    except Exception as e:
        print(f"[ReviewRoute] Error in fix_draft: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-fix engine failed: {str(e)}")


def load_docx_bytes(content_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content_bytes))
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def load_rtf_bytes(content_bytes: bytes) -> str:
    from striprtf.striprtf import rtf_to_text
    raw = content_bytes.decode("cp1252", errors="ignore")
    return rtf_to_text(raw).strip()
