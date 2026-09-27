import json
import os
import sys
import time
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm import call_llm
from services.translate_output import SUPPORTED_LANGUAGES

LOCALES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend/src/locales'))

LANG_TO_FILE = {
    "hindi": "hi.json",
    "marathi": "mr.json",
    "bengali": "bn.json",
    "tamil": "ta.json",
    "telugu": "te.json",
    "kannada": "kn.json",
    "gujarati": "gu.json",
    "malayalam": "ml.json",
    "punjabi": "pa.json",
    "odia": "or.json",
}

def extract_json_block(text: str) -> str:
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        return match.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text

def translate_json_chunk(chunk_dict: dict, lang_name: str, desc: str) -> dict:
    prompt = (
        f"You are an expert legal and UI translator for Indian legal software (LexSetu). "
        f"Translate all string values in the following JSON object into {desc}. "
        f"CRITICAL RULES:\n"
        f"1. Keep all JSON keys exactly in English as provided.\n"
        f"2. Keep __VAR_xxx__ tokens EXACTLY unchanged (e.g. __VAR_count__, __VAR_score__, __VAR_title__, __VAR_language__, __VAR_years__, __VAR_current__, __VAR_total__).\n"
        f"3. Keep legal statute references (e.g. 'IPC', 'CrPC', 'BNSS', 'BNS', 'Section 108') and Act names in English Latin script.\n"
        f"4. Status markers like [NOT PROVIDED], [NOT IN INDEX], [VERIFIED] should preserve their bracket format.\n"
        f"5. Output ONLY the translated JSON. No introduction, no markdown, no explanation."
    )
    raw = json.dumps(chunk_dict, ensure_ascii=False, indent=2)
    # Mask {{var}} to __VAR_var__
    masked_raw = re.sub(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', r'__VAR_\1__', raw)

    response = call_llm(prompt, masked_raw)
    cleaned = extract_json_block(response)
    # Unmask __VAR_var__ to {{var}}
    unmasked = re.sub(r'__VAR_([a-zA-Z0-9_]+)__', r'{{\1}}', cleaned)

    try:
        return json.loads(unmasked)
    except Exception as e:
        print(f"  [JSON Parse Warning] {lang_name}: {e}. Retrying cleanup...")
        time.sleep(1)
        retry_prompt = "Return ONLY valid JSON matching this content:\n" + unmasked
        resp2 = call_llm(retry_prompt, "")
        c2 = extract_json_block(resp2)
        c2 = re.sub(r'__VAR_([a-zA-Z0-9_]+)__', r'{{\1}}', c2)
        return json.loads(c2)

def main():
    en_path = os.path.join(LOCALES_DIR, "en.json")
    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)

    sections_to_check = ["verifyFiling", "legalAid", "draftAssistant", "draftReview"]

    for lang_key, filename in LANG_TO_FILE.items():
        file_path = os.path.join(LOCALES_DIR, filename)
        desc = SUPPORTED_LANGUAGES[lang_key]
        print(f"\nProcessing {lang_key} ({filename})...")
        
        target_data = {}
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    target_data = json.load(f)
                except Exception:
                    target_data = {}

        updated = False
        for sec in sections_to_check:
            is_missing = sec not in target_data
            is_incomplete_draft = (sec == "draftAssistant" and "categories" not in target_data.get(sec, {}))
            is_missing_review = (sec == "draftReview" and sec not in target_data)

            if is_missing or is_missing_review:
                print(f"  Translating section '{sec}' for {lang_key}...")
                chunk = en_data.get(sec, {})
                try:
                    translated_sec = translate_json_chunk(chunk, lang_key, desc)
                    target_data[sec] = translated_sec
                    updated = True
                    print(f"  ✓ Section '{sec}' translated.")
                except Exception as e:
                    print(f"  ✗ Failed '{sec}' for {lang_key}: {e}")
            elif is_incomplete_draft:
                print(f"  Updating incomplete '{sec}' for {lang_key}...")
                chunk = en_data.get(sec, {})
                try:
                    translated_sec = translate_json_chunk(chunk, lang_key, desc)
                    merged = {**translated_sec, **target_data[sec]}
                    merged["categories"] = translated_sec.get("categories", chunk.get("categories", {}))
                    merged["templates"] = translated_sec.get("templates", chunk.get("templates", {}))
                    merged["fields"] = translated_sec.get("fields", chunk.get("fields", {}))
                    merged["stages"] = translated_sec.get("stages", chunk.get("stages", {}))
                    target_data[sec] = merged
                    updated = True
                    print(f"  ✓ Sub-keys for '{sec}' updated.")
                except Exception as e:
                    print(f"  ✗ Failed updating '{sec}' for {lang_key}: {e}")

        if updated:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(target_data, f, ensure_ascii=False, indent=2)
            print(f"✓ Saved {filename} ({len(target_data)} sections).")
        else:
            print(f"✓ All sections already present in {filename}.")

if __name__ == "__main__":
    main()
