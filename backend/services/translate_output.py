"""
translate_output.py
====================
Generalizes the Hindi-only "regional-language grounded mode" (see
citation_verifier.render_report_in_language, the original single-feature
version of this idea) into a single, app-wide translation step usable by
every feature.

NON-NEGOTIABLE RULE: this module runs ONLY on already-generated,
already-verified English text. Retrieval, citation-matching, and legal
reasoning always happen in English, before this is ever called. Language
selection is a rendering step strictly after verification -- never a
substitute for it. Nothing here re-runs retrieval, re-verifies a citation, or
re-generates legal reasoning in the target language.
"""

from services.llm import call_llm

# Eighth-Schedule-first curated list (matches frontend LanguageContext).
# Adding a language later is a one-line addition here + the frontend list --
# nothing else hardcodes "Hindi".
SUPPORTED_LANGUAGES = {
    "hindi": "Hindi, written in the Devanagari script",
    "marathi": "Marathi, written in the Devanagari script",
    "bengali": "Bengali, written in the Bengali script",
    "tamil": "Tamil, written in the Tamil script",
    "telugu": "Telugu, written in the Telugu script",
    "kannada": "Kannada, written in the Kannada script",
    "gujarati": "Gujarati, written in the Gujarati script",
    "malayalam": "Malayalam, written in the Malayalam script",
    "punjabi": "Punjabi, written in the Gurmukhi script",
    "odia": "Odia, written in the Odia script",
}

LANGUAGE_ALIASES = {
    "hi": "hindi",
    "mr": "marathi",
    "bn": "bengali",
    "ta": "tamil",
    "te": "telugu",
    "kn": "kannada",
    "gu": "gujarati",
    "ml": "malayalam",
    "pa": "punjabi",
    "or": "odia",
    "od": "odia",
    "panjabi": "punjabi",
}


def normalize_target_language(target_lang: str) -> str:
    """Resolve 2-letter or alternative code to canonical SUPPORTED_LANGUAGES key."""
    if not target_lang:
        return "hindi"
    key = target_lang.lower().strip()
    return LANGUAGE_ALIASES.get(key, key)


TRANSLATION_DISCLAIMER = "Translated from English — verification was performed in English"


def translate_grounded_output(text: str, source_citations: list, target_lang: str) -> dict:
    """Translate an already-verified English result for display only.

    Args:
        text: The already-generated, already-verified English text (a Legal
            Aid answer, a generated draft, a review summary, a contradiction
            analysis result, ...).
        source_citations: Citations/sources attached to the original English
            result. Passed through completely unchanged -- translation never
            touches citation data, only the surrounding prose.
        target_lang: One of SUPPORTED_LANGUAGES' keys or 2-letter aliases.

    Returns:
        A dict with the translated text, the untouched citations, the
        target language, and a mandatory disclaimer. Never cache this as if
        it were a fresh verification result -- it is always a derived,
        translated VIEW of an English original.
    """
    resolved_lang = normalize_target_language(target_lang)
    if resolved_lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {target_lang!r}. Use one of {list(SUPPORTED_LANGUAGES)}.")

    if not text or not text.strip():
        return {
            "translated_text": text or "",
            "source_citations": source_citations or [],
            "target_lang": resolved_lang,
            "disclaimer": TRANSLATION_DISCLAIMER,
        }

    system_prompt = (
        f"Translate the following English legal text into {SUPPORTED_LANGUAGES[resolved_lang]}. "
        "Preserve every status marker such as [Not Provided], [Mismatch], [Verified], "
        "[REQUIRES VERIFICATION], or similar bracketed markers -- keep them as-is or use "
        "their natural equivalent phrase in the target language, but never drop them. Do "
        "not add or remove any legal claim, fact, or nuance from the original. "
        "Case names, court names, citation strings, section numbers, and Act names MUST "
        "stay exactly as written in the original English, in the Latin/Roman alphabet -- "
        "do not transliterate them into the target script and do not translate them (e.g. "
        "keep 'Section 108' and 'Transfer of Property Act, 1882' exactly as-is, do not "
        "render them phonetically in the target script). Translate only the surrounding "
        "descriptive language. Respond with ONLY the translated text -- no preamble, no "
        "commentary, no markdown code fences."
    )
    translated_text = call_llm(system_prompt, text, max_tokens=1500)

    return {
        "translated_text": translated_text,
        "source_citations": source_citations or [],
        "target_lang": resolved_lang,
        "disclaimer": TRANSLATION_DISCLAIMER,
    }
