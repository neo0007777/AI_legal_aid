import os
import json
import re
import time

CANDIDATE_GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

_ACTIVE_GROQ_MODEL = None
_DEGRADED_MODELS = {}  # model_name -> float timestamp when cooldown expires


def get_active_model() -> str:
    global _ACTIVE_GROQ_MODEL, _DEGRADED_MODELS
    now = time.time()
    if _ACTIVE_GROQ_MODEL and _DEGRADED_MODELS.get(_ACTIVE_GROQ_MODEL, 0) < now:
        return _ACTIVE_GROQ_MODEL
    preferred = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    if _DEGRADED_MODELS.get(preferred, 0) < now:
        return preferred
    for m in CANDIDATE_GROQ_MODELS:
        if _DEGRADED_MODELS.get(m, 0) < now:
            return m
    return preferred


def call_groq(system_prompt: str, user_message: str, json_mode: bool = False, model: str = None, max_tokens: int = None) -> str:
    from groq import Groq
    global _ACTIVE_GROQ_MODEL

    target_model = model or get_active_model()
    # 45s timeout to allow full legal document generation without prematurely timing out
    client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=45.0, max_retries=0)

    # Estimate prompt tokens roughly (1 token ~ 3.5 chars) to prevent exceeding TPM 8000
    est_prompt_tokens = int((len(system_prompt) + len(user_message)) / 3.5)

    # Respect free tier token limits:
    # qwen/qwen3.8-27b has an enforced hard ceiling of 1000 OTPM (output tokens per minute)
    if "qwen" in target_model.lower():
        default_budget = min(max_tokens, 750) if max_tokens else 750
    else:
        default_budget = min(max_tokens, 2048) if max_tokens else 1500

    # Prevent TPM overflow: keep total requested tokens safely under 7600
    max_allowed = max(350, 7600 - est_prompt_tokens)
    tokens_limit = min(default_budget, max_allowed)

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

    # For reasoning models (gpt-oss-20b, gpt-oss-120b), keep reasoning low and parsed
    # to prevent reasoning tokens from consuming the output budget and stalling generation
    if "gpt-oss" in target_model.lower():
        kwargs["extra_body"] = {
            "reasoning_format": "parsed",
            "reasoning_effort": "low",
        }

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    raw_content = choice.message.content or ""

    # If content is empty but model emitted reasoning, use reasoning as safety fallback
    if not raw_content.strip() and hasattr(choice.message, "reasoning"):
        reasoning_text = getattr(choice.message, "reasoning", "") or ""
        if reasoning_text.strip():
            raw_content = reasoning_text

    clean_content = raw_content.strip()
    if not clean_content:
        raise ValueError(f"Model '{target_model}' returned empty content (finish_reason: {choice.finish_reason})")

    _ACTIVE_GROQ_MODEL = target_model
    return clean_content


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


def call_llm(system_prompt: str, user_message: str, json_mode: bool = False, force_local: bool = False, max_tokens: int = None) -> str:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    groq_key = os.getenv("GROQ_API_KEY", "")
    use_groq = (not force_local) and groq_key and groq_key != "your_groq_api_key_here"

    if use_groq:
        now = time.time()
        preferred_model = get_active_model()
        candidates = [preferred_model] + [m for m in CANDIDATE_GROQ_MODELS if m != preferred_model]
        # Filter out models currently in rate-limit cooldown
        healthy_models = [m for m in candidates if _DEGRADED_MODELS.get(m, 0) < now]
        models_to_try = healthy_models if healthy_models else candidates

        for target_model in models_to_try:
            try:
                return call_groq(system_prompt, user_message, json_mode=json_mode, model=target_model, max_tokens=max_tokens)
            except Exception as e:
                err_str = str(e)
                print(f"[LLM] Groq model '{target_model}' failed: {e}")

                # Immediate failover on rate limit
                if "rate_limit" in err_str or "429" in err_str or "limit reached" in err_str.lower():
                    # Check if OTPM exceeded limit directly (e.g. requested > 1000)
                    if "otpm" in err_str.lower() and "reduce max_tokens" in err_str.lower():
                        print(f"[LLM] Model '{target_model}' OTPM ceiling hit. Immediate retry with 700 tokens...")
                        try:
                            return call_groq(system_prompt, user_message, json_mode=json_mode, model=target_model, max_tokens=700)
                        except Exception as otpm_retry_err:
                            err_str = str(otpm_retry_err)

                    # Check for remaining budget in current window (e.g. Limit 1000, Used 681)
                    limit_used_match = re.search(r"limit\s+(\d+),\s+used\s+(\d+)", err_str.lower())
                    if limit_used_match:
                        lim = int(limit_used_match.group(1))
                        usd = int(limit_used_match.group(2))
                        rem = lim - usd
                        if rem >= 300:
                            print(f"[LLM] Retrying '{target_model}' with available remaining budget {rem - 20}...")
                            try:
                                return call_groq(system_prompt, user_message, json_mode=json_mode, model=target_model, max_tokens=rem - 20)
                            except Exception as rem_retry_err:
                                err_str = str(rem_retry_err)

                    # Check for transient burst limit (e.g. 'Please try again in 4.5s')
                    wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", err_str.lower())
                    if wait_match:
                        wait_sec = float(wait_match.group(1))
                        if wait_sec <= 35.0:
                            print(f"[LLM] Burst wait of {wait_sec:.2f}s detected for '{target_model}'. Waiting for rate-limit window to slide...")
                            time.sleep(wait_sec + 0.6)
                            try:
                                return call_groq(system_prompt, user_message, json_mode=json_mode, model=target_model, max_tokens=max_tokens)
                            except Exception as burst_retry_err:
                                print(f"[LLM] Burst retry failed: {burst_retry_err}")
                                err_str = str(burst_retry_err)

                    # If TPM limit, try compressed payload before giving up on this model
                    if "per minute" in err_str.lower() or "tpm" in err_str.lower() or "otpm" in err_str.lower():
                        _DEGRADED_MODELS[target_model] = time.time() + 20
                        print(f"[LLM] Model '{target_model}' TPM/OTPM limit reached (cooldown 20s). Trying compressed retry...")
                        try:
                            trimmed_user = user_message[:2000] if len(user_message) > 2000 else user_message
                            trimmed_sys = system_prompt[:4500] if len(system_prompt) > 4500 else system_prompt
                            return call_groq(trimmed_sys, trimmed_user, json_mode=json_mode, model=target_model, max_tokens=min(max_tokens or 700, 600))
                        except Exception as retry_tpm_err:
                            print(f"[LLM] Compressed TPM retry for '{target_model}' failed: {retry_tpm_err}")
                        continue
                    else:
                        # Tokens per day (TPD) limit: longer cooldown so we don't repeatedly hammer exhausted model
                        _DEGRADED_MODELS[target_model] = time.time() + 1800
                        print(f"[LLM] Model '{target_model}' TPD limit reached (cooldown 30m). Failing over.")
                        continue

                # If request payload was too large for TPM limit
                if "413" in err_str or "too large" in err_str.lower():
                    try:
                        trimmed_user = user_message[:2500] if len(user_message) > 2500 else user_message
                        trimmed_sys = system_prompt[:6000] if len(system_prompt) > 6000 else system_prompt
                        return call_groq(trimmed_sys, trimmed_user, json_mode=json_mode, model=target_model, max_tokens=min(max_tokens or 1000, 900))
                    except Exception as retry_tpm_err:
                        print(f"[LLM] Compressed 413 retry for '{target_model}' failed: {retry_tpm_err}")

                if "model_not_found" in err_str or "does not exist" in err_str or "404" in err_str:
                    _DEGRADED_MODELS[target_model] = time.time() + 3600
                    continue

                continue

    try:
        return call_ollama(system_prompt, user_message, json_mode=json_mode)
    except Exception as e:
        print(f"[LLM] Ollama fallback failed: {e}")

    return json.dumps({
        "error": "AI service temporarily unavailable. Please try again."
    }) if json_mode else "⚠️ AI service temporarily unavailable. Please try again."