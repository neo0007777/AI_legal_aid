import os
import sys
import json
import re
import time
import dotenv

dotenv.load_dotenv('backend/.env')
sys.path.insert(0, 'backend')
from services.llm import call_llm

LANG_NAMES = {
    "hi": "Hindi",
    "gu": "Gujarati",
    "mr": "Marathi",
    "ta": "Tamil",
    "bn": "Bengali",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "or": "Odia",
}

def mask_vars(s):
    if not isinstance(s, str):
        return s
    return re.sub(r'\{\{([a-zA-Z0-9_]+)\}\}', r'__VAR_\1__', s)

def unmask_vars(s):
    if not isinstance(s, str):
        return s
    return re.sub(r'__VAR_([a-zA-Z0-9_]+)__', r'{{\1}}', s)

def translate_batch(batch: dict, lang_name: str) -> dict:
    masked_batch = {k: mask_vars(v) for k, v in batch.items()}
    prompt = (
        f"Translate the values of this UI and legal text JSON object into {lang_name}. "
        "Keep exact keys. Preserve placeholders like __VAR_count__ exactly as-is. "
        "Do not translate English legal case names or Section numbers (e.g. keep 'Section 438 CrPC'). "
        "Return valid JSON only."
    )
    for attempt in range(5):
        try:
            res_str = call_llm(prompt, json.dumps(masked_batch), json_mode=True)
            cleaned = res_str.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()
            data = json.loads(cleaned)
            return {k: unmask_vars(data.get(k, v)) for k, v in batch.items()}
        except Exception as e:
            print(f"  [Attempt {attempt+1}] Error: {e}, waiting 8s...")
            time.sleep(8)
    # Fallback to English batch if all attempts fail
    return batch

def sync_locale(lang_code: str):
    lang_name = LANG_NAMES.get(lang_code)
    if not lang_name:
        print(f"Unknown language code: {lang_code}")
        return

    en_path = 'frontend/src/locales/en.json'
    target_path = f'frontend/src/locales/{lang_code}.json'

    with open(en_path, 'r', encoding='utf-8') as f:
        en = json.load(f)

    if os.path.exists(target_path):
        with open(target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)
    else:
        target = {}

    total_added = 0

    for section, sec_data in en.items():
        if section not in target:
            target[section] = {}

        missing_keys = {
            k: v for k, v in sec_data.items()
            if k not in target[section] or (target[section][k] == v and len(v) > 4 and k not in ['english', 'en', 'code'])
        }
        if not missing_keys:
            continue

        print(f"[{lang_code} - {lang_name}] Section '{section}': {len(missing_keys)} keys to translate")

        # Chunk into smaller batches (6 for draftAssistant to prevent max completion tokens reached, 8 for others)
        items = list(missing_keys.items())
        batch_size = 6 if section == 'draftAssistant' else 8
        for i in range(0, len(items), batch_size):
            chunk = dict(items[i:i+batch_size])
            translated_chunk = translate_batch(chunk, lang_name)
            for k, val in translated_chunk.items():
                target[section][k] = val
                total_added += 1
            print(f"  Processed {min(i+batch_size, len(items))}/{len(items)} keys in {section}")
            time.sleep(3.5)

    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(target, f, indent=2, ensure_ascii=False)

    print(f"[{lang_code} - {lang_name}] Completed! Added {total_added} keys. Saved to {target_path}.\n")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        for code in sys.argv[1:]:
            sync_locale(code)
    else:
        print("Usage: python3 sync_one_locale.py <lang_code> ...")
