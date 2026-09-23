import os
import json
import re
import time

CANDIDATE_GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "groq/compound-mini",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

_ACTIVE_GROQ_MODEL = None


def get_active_model() -> str:
    global _ACTIVE_GROQ_MODEL
    if _ACTIVE_GROQ_MODEL:
        return _ACTIVE_GROQ_MODEL
    return os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def call_groq(system_prompt: str, user_message: str, json_mode: bool = False, model: str = None) -> str:
    from groq import Groq
    global _ACTIVE_GROQ_MODEL

    client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=25.0)
    target_model = model or get_active_model()

    # Respect free tier token limits (qwen has a strict 1000 OTPM limit on free tier)
    tokens_limit = 750 if "qwen" in target_model.lower() else 2048

    kwargs = dict(
        model=target_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=tokens_limit,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    _ACTIVE_GROQ_MODEL = target_model
    return response.choices[0].message.content.strip()


def call_ollama(system_prompt: str, user_message: str, json_mode: bool = False) -> str:
    import ollama
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")

    kwargs = dict(
        model=ollama_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    if json_mode:
        kwargs["format"] = "json"

    response = ollama.chat(**kwargs)
    return response["message"]["content"].strip()


def call_llm(system_prompt: str, user_message: str, json_mode: bool = False, force_local: bool = False) -> str:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    groq_key = os.getenv("GROQ_API_KEY", "")
    # S3 Task 4 (local-only mode): force_local skips Groq entirely regardless of
    # whether a valid key is configured, so the frontend's local-only toggle is a
    # real behavior switch, not cosmetic. Only applies to call_llm's cascade
    # (draft generation, etc) -- citation entailment is pinned to Groq by
    # deliberate S2 design and is not routed through this function's fallback.
    use_groq = (not force_local) and groq_key and groq_key != "your_groq_api_key_here"

    if use_groq:
        preferred_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        models_to_try = [preferred_model] + [m for m in CANDIDATE_GROQ_MODELS if m != preferred_model]

        for target_model in models_to_try:
            try:
                return call_groq(system_prompt, user_message, json_mode=json_mode, model=target_model)
            except Exception as e:
                err_str = str(e)
                print(f"[LLM] Groq model '{target_model}' failed: {e}")

                # If rate limited or model not found, try next candidate model immediately
                if "rate_limit" in err_str or "model_not_found" in err_str or "does not exist" in err_str or "429" in err_str or "404" in err_str:
                    print(f"[LLM] Switching to next candidate model due to: {e}")
                    continue

                # For other errors, do a quick retry with backoff
                time.sleep(1.5)
                try:
                    return call_groq(system_prompt, user_message, json_mode=json_mode, model=target_model)
                except Exception as retry_err:
                    print(f"[LLM] Groq retry for '{target_model}' failed: {retry_err}")
                    continue

    try:
        return call_ollama(system_prompt, user_message, json_mode=json_mode)
    except Exception as e:
        print(f"[LLM] Ollama fallback failed: {e}")

    return json.dumps({
        "error": "AI service temporarily unavailable. Please try again."
    }) if json_mode else "⚠️ AI service temporarily unavailable. Please try again."