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

    res = run_hybrid_review(extracted_text, document_type, fact_manifest=manifest, procedural_posture=posture)
    res.extracted_text = extracted_text
    return res


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
        if isinstance(e, HTTPException):
            raise e
        print(f"[ReviewRoute] Error in fix_draft: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-fix engine failed: {str(e)}")


from pydantic import BaseModel
from services.translate_output import SUPPORTED_LANGUAGES, normalize_target_language, TRANSLATION_DISCLAIMER, translate_grounded_output
from services.llm import call_groq
import hashlib

_REVIEW_TRANSLATION_CACHE = {}


class TranslateReportRequest(BaseModel):
    report: dict
    target_lang: str


@router.post("/translate-report")
def translate_review_report(req: TranslateReportRequest):
    """Translates the analysis report (summary, issues, recommendations) to the target language."""
    resolved_lang = normalize_target_language(req.target_lang)
    if resolved_lang not in SUPPORTED_LANGUAGES or resolved_lang == "english":
        return req.report

    rep = req.report
    cache_key = hashlib.sha256(f"{resolved_lang}:{json.dumps(rep, sort_keys=True)}".encode("utf-8")).hexdigest()
    if cache_key in _REVIEW_TRANSLATION_CACHE:
        return _REVIEW_TRANSLATION_CACHE[cache_key]

    payload_to_translate = {
        "summary": rep.get("summary", ""),
        "document_type": rep.get("document_type", ""),
        "missing_sections": rep.get("missing_sections", []),
        "critical": [
            {"id": x.get("id"), "title": x.get("title", ""), "description": x.get("description", ""), "suggested_fix": x.get("suggested_fix", "")}
            for x in rep.get("critical", [])
        ],
        "warnings": [
            {"id": x.get("id"), "title": x.get("title", ""), "description": x.get("description", ""), "suggested_fix": x.get("suggested_fix", "")}
            for x in rep.get("warnings", [])
        ],
        "suggestions": [
            {"id": x.get("id"), "title": x.get("title", ""), "description": x.get("description", ""), "suggested_fix": x.get("suggested_fix", "")}
            for x in rep.get("suggestions", [])
        ],
    }

    target_lang_desc = SUPPORTED_LANGUAGES[resolved_lang]
    prompt = (
        f"Translate the values of this legal review report into {target_lang_desc}. "
        "Keep exact keys and structure. Keep Section numbers, Case names, and Act names in English. "
        "Return valid JSON only."
    )
    try:
        translated_json_str = call_llm(prompt, json.dumps(payload_to_translate), json_mode=True)
        cleaned = translated_json_str.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        translated_data = json.loads(cleaned)

        result = dict(rep)
        result["summary"] = translated_data.get("summary", rep.get("summary", ""))
        result["document_type"] = translated_data.get("document_type", rep.get("document_type", ""))
        result["missing_sections"] = translated_data.get("missing_sections", rep.get("missing_sections", []))
        if "critical" in translated_data:
            result["critical"] = translated_data["critical"]
        if "warnings" in translated_data:
            result["warnings"] = translated_data["warnings"]
        if "suggestions" in translated_data:
            result["suggestions"] = translated_data["suggestions"]
        result["disclaimer"] = TRANSLATION_DISCLAIMER
        result["target_lang"] = resolved_lang

        _REVIEW_TRANSLATION_CACHE[cache_key] = result
        return result
    except Exception as e:
        print(f"[ReviewRoute] translate_review_report notice: {e}")
        return rep


class TranslateFixRequest(BaseModel):
    corrected_draft: str
    changes_made: list[str] = []
    target_lang: str


@router.post("/translate-fix")
def translate_fix_results(req: TranslateFixRequest):
    """Translates the auto-fixed draft and changes_made list to the target language."""
    resolved_lang = normalize_target_language(req.target_lang)
    if resolved_lang not in SUPPORTED_LANGUAGES or resolved_lang == "english":
        return {
            "translated_corrected_draft": req.corrected_draft,
            "translated_changes_made": req.changes_made,
            "target_lang": "english",
        }

    translated_draft = ""
    if req.corrected_draft.strip():
        draft_res = translate_grounded_output(req.corrected_draft, [], resolved_lang)
        translated_draft = draft_res.get("translated_text", "")

    translated_changes = req.changes_made
    if req.changes_made:
        try:
            target_lang_desc = SUPPORTED_LANGUAGES[resolved_lang]
            changes_prompt = f"Translate this list of remediation actions into {target_lang_desc}. Keep legal section numbers and Acts in English. Return valid JSON only with a 'changes' key containing the list."
            res_str = call_llm(changes_prompt, json.dumps({"changes": req.changes_made}), json_mode=True)
            cleaned = res_str.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()
            data = json.loads(cleaned)
            translated_changes = data.get("changes", req.changes_made)
        except Exception as e:
            print(f"[ReviewRoute] translate changes notice: {e}")

    return {
        "translated_corrected_draft": translated_draft,
        "translated_changes_made": translated_changes,
        "target_lang": resolved_lang,
        "disclaimer": TRANSLATION_DISCLAIMER,
    }


def load_docx_bytes(content_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content_bytes))
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def load_rtf_bytes(content_bytes: bytes) -> str:
    from striprtf.striprtf import rtf_to_text
    raw = content_bytes.decode("cp1252", errors="ignore")
    return rtf_to_text(raw).strip()
