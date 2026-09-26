import hashlib

from fastapi import APIRouter, HTTPException, Depends

from models.database import User
from models.schemas import TranslateRequest, TranslateResponse
from services.translate_output import translate_grounded_output, SUPPORTED_LANGUAGES
from utils.auth import get_current_user

router = APIRouter()

# Hackathon-scope in-memory cache, same pattern as citations.py's _REPORT_STORE:
# not persisted, not shared across processes -- fine for a single-worker
# dev/demo deploy. Keyed by a hash of (source_type, target_lang, text) so
# re-requesting the same translation never re-calls the LLM.
_TRANSLATION_CACHE = {}


def _cache_key(source_type: str, target_lang: str, text: str) -> str:
    raw = f"{source_type}:{target_lang}:{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@router.get("/languages")
def list_languages():
    return {"languages": list(SUPPORTED_LANGUAGES.keys())}


@router.post("", response_model=TranslateResponse)
def translate(body: TranslateRequest, current_user: User = Depends(get_current_user)):
    if body.target_lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"target_lang must be one of {list(SUPPORTED_LANGUAGES)}.")
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="No English source text to translate.")

    key = _cache_key(body.source_type, body.target_lang, body.text)
    if key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[key]

    try:
        result = translate_grounded_output(body.text, body.citations or [], body.target_lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[Translate] translate_grounded_output failed: {e}")
        raise HTTPException(status_code=503, detail="Translation service was unavailable. Please try again.")

    _TRANSLATION_CACHE[key] = result
    return result
