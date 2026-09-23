import asyncio
import json
import re
import threading
import time
from difflib import SequenceMatcher

from services.judgment_search import search_judgments, get_coverage_banner
from services.llm import call_llm, call_groq

# S2 brief: pin entailment to gpt-oss-120b specifically. No cascade fallback — if this
# model call fails, the cautious-bias rule below treats it as "unclear" (-> Mismatch)
# rather than silently retrying on a weaker model that could produce a false Verified.
ENTAILMENT_MODEL = "openai/gpt-oss-120b"

# Groq's free tier caps gpt-oss-120b at 8000 tokens/minute. Firing every citation's
# entailment call at once (observed with 5 concurrent citations in testing) blows
# through that budget and produces real 429s -- which the cautious-bias rule then
# turns into Mismatch en masse, even for citations that are actually correct. This
# throttles only the Groq-calling step (Qdrant search stays fully concurrent), which
# keeps checking genuinely parallel while staying under the rate limit.
_ENTAILMENT_CONCURRENCY = 3
_entailment_semaphore = threading.Semaphore(_ENTAILMENT_CONCURRENCY)

_RETRY_AFTER_PATTERN = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)

# Case-identity match uses string similarity on names, not vector score, since Qdrant's
# score reflects semantic similarity of chunk TEXT, not whether it's the same case.
CASE_NAME_MATCH_THRESHOLD = 0.55

_SUFFIX_WORDS = {"ors", "anr", "others", "another", "etc", "and", "the", "vs", "versus", "v"}

# Generic party words (govt/institutional litigants) that recur across thousands of
# unrelated Indian cases ("X v. State of Rajasthan", "Y v. Union of India"...). Overlap
# on these alone must never be enough to call two citations the same case -- see the
# false match caught in testing: a fabricated "Ramesh Kumar v. State of Rajasthan"
# otherwise scored above threshold against an unrelated real "... v. State of Rajasthan".
_GENERIC_PARTY_WORDS = {
    "state", "union", "india", "government", "govt", "central", "board", "corporation",
    "authority", "commissioner", "secretary", "director", "territory", "nct", "of",
    "municipal", "council", "department", "ministry",
    # State/UT names: boilerplate respondents ("X v. State of Rajasthan") recur across
    # thousands of unrelated cases, so the state name alone must never count as the
    # "distinctive" token that makes two citations look like the same case.
    "andhra", "pradesh", "arunachal", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
    "haryana", "himachal", "jharkhand", "karnataka", "kerala", "madhya", "maharashtra",
    "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
    "rajasthan", "sikkim", "tamil", "nadu", "telangana", "tripura", "uttar", "uttarakhand",
    "bengal", "west", "delhi", "andaman", "nicobar", "chandigarh", "dadra", "nagar",
    "haveli", "daman", "diu", "lakshadweep", "puducherry", "jammu", "kashmir", "ladakh",
}


def _normalize_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    tokens = [t for t in name.split() if t not in _SUFFIX_WORDS]
    return " ".join(tokens)


def _name_similarity(a: str, b: str) -> float:
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    set_a, set_b = set(na.split()), set(nb.split())
    jaccard = len(set_a & set_b) / len(set_a | set_b) if (set_a or set_b) else 0.0
    score = max(ratio, jaccard)

    # Require the two names to share at least one DISTINCTIVE token (not a bare
    # generic-party word) -- otherwise two different cases against "the State" can
    # score high purely on the shared boilerplate respondent.
    distinctive_overlap = {t for t in (set_a & set_b) if t not in _GENERIC_PARTY_WORDS and len(t) > 3}
    if not distinctive_overlap:
        score = min(score, 0.4)

    return score


CITATION_EXTRACTION_SYSTEM_PROMPT = """You extract case-law citations from Indian legal filings.

For every place the filing cites or relies on a court judgment, extract:
- "case_name": the party names as written in the filing (e.g. "Swiss Ribbons Pvt. Ltd. v. Union of India"). Copy it VERBATIM from the text — do not correct, expand, or normalize it.
- "citation_string": the reporter/neutral citation if given (e.g. "(2019) 4 SCC 17", "2019 INSC 95"), else "".
- "claimed_content": the specific proposition, holding, or quoted text the filing attributes to this case — the actual legal claim being made, in the filing's own words. This is what gets fact-checked, so be precise and include the surrounding sentence(s), not just the case name.
- "context_snippet": a short verbatim excerpt (under 200 chars) from the filing surrounding the citation, for anchoring.

Rules:
- Only extract citations that ACTUALLY APPEAR in the given text. Never invent a citation, case name, or claim that isn't in the input.
- If the same case is cited more than once with different claims, extract each occurrence separately.
- If a case is named but no specific claim/holding is attributed to it (just a bare mention), still extract it with claimed_content describing what point it's cited for, as best you can tell from context.

Respond with ONLY a JSON object: {"citations": [{"case_name": "...", "citation_string": "...", "claimed_content": "...", "context_snippet": "..."}]}
If there are no citations, respond {"citations": []}.
"""

_CHUNK_SIZE = 6000
_CHUNK_OVERLAP = 300


def _chunk_text(text: str) -> list:
    if len(text) <= _CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - _CHUNK_OVERLAP
    return chunks


def _parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


def extract_citations(filing_text: str) -> tuple:
    """Citation classifier. Uses the default LLM cascade (call_llm) — unlike entailment,
    extraction quality degrading gracefully across the cascade is acceptable here since
    every extracted citation is verified against the source text below before being trusted.

    Returns (citations, incomplete) -- incomplete=True if any chunk's extraction call
    failed outright (e.g. every cascade model + Ollama fallback unavailable), so the
    caller can warn the user rather than silently presenting a partial citation list
    as if it were the complete one. Caught in UX audit: under Groq quota exhaustion, a
    multi-chunk filing silently lost citations from the failed chunk with no signal."""
    all_citations = []
    seen = set()
    incomplete = False

    for chunk in _chunk_text(filing_text):
        raw = call_llm(CITATION_EXTRACTION_SYSTEM_PROMPT, chunk, json_mode=True)
        data = _parse_json_object(raw)
        # A weaker cascade model (more likely under Groq quota pressure, when
        # the pinned model falls back further down CANDIDATE_GROQ_MODELS) can
        # ignore the "wrap in {citations: [...]}" instruction and return a
        # bare JSON array instead -- this crashed with AttributeError on
        # data.get(...) before this guard, caught via live re-testing.
        if isinstance(data, list):
            data = {"citations": data}
        if not isinstance(data, dict):
            print(f"[CitationVerifier] Citation extraction returned unexpected JSON shape for one chunk: {raw[:200]!r}")
            incomplete = True
            continue
        if "error" in data and "citations" not in data:
            print(f"[CitationVerifier] Citation extraction failed for one chunk: {data.get('error')}")
            incomplete = True
            continue
        for c in data.get("citations", []):
            if not isinstance(c, dict):
                continue
            case_name = (c.get("case_name") or "").strip()
            if not case_name:
                continue

            # Anti-hallucination guard: the extracted case name must actually appear
            # (fuzzily) in the source chunk, or we drop it. An LLM inventing a citation
            # that isn't in the filing would corrupt the whole report.
            if not _appears_in_text(case_name, chunk):
                print(f"[CitationVerifier] Dropped unverifiable extraction (not found in source text): {case_name}")
                continue

            key = _normalize_name(case_name) + "|" + (c.get("citation_string") or "").strip().lower()
            if key in seen:
                continue
            seen.add(key)

            all_citations.append({
                "case_name": case_name,
                "citation_string": (c.get("citation_string") or "").strip(),
                "claimed_content": (c.get("claimed_content") or "").strip(),
                "context_snippet": (c.get("context_snippet") or "").strip(),
            })

    return all_citations, incomplete


def _appears_in_text(case_name: str, text: str) -> bool:
    # Require at least one distinctive (>3 char) token from the case name to appear
    # verbatim in the source text — cheap, robust guard against wholesale invention.
    tokens = [t for t in _normalize_name(case_name).split() if len(t) > 3]
    if not tokens:
        return case_name.lower() in text.lower()
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits >= max(1, len(tokens) // 3)


def resolve_case(case_name: str, citation_string: str) -> dict:
    """Layer 1, step 1: identify which indexed judgment (if any) this citation refers to.
    Returns None (-> 'Not found in indexed corpus') if nothing in the corpus is
    confidently the same case — this is what correctly handles both fabricated case
    names AND real-but-out-of-corpus citations (pre-2016, non-SC, etc.)."""
    query = f"{case_name} {citation_string}".strip()
    hits = search_judgments(query, top_k=5)
    if not hits:
        return None

    best_hit, best_score = None, 0.0
    for h in hits:
        sim = _name_similarity(case_name, h["metadata"]["case_name"])
        if sim > best_score:
            best_score, best_hit = sim, h

    if best_hit is None or best_score < CASE_NAME_MATCH_THRESHOLD:
        return None

    return {**best_hit["metadata"], "_name_match_score": best_score}


ENTAILMENT_SYSTEM_PROMPT = """You are checking whether a real Supreme Court of India judgment actually supports a claim a legal filing attributes to it.

You will be given:
1. CLAIM — what the filing says this case holds/says.
2. RETRIEVED TEXT — actual excerpted text from the real judgment (the best-matching passage(s) found for this claim within this specific case).

Decide:
- "entailed": the retrieved text clearly supports/states the claim.
- "contradicted": the retrieved text clearly says something different from or opposite to the claim.
- "unclear": the retrieved text is on-topic but doesn't clearly confirm or deny the specific claim (e.g. the relevant passage wasn't retrieved, or the claim is more specific than what's shown).

Also give a confidence: "high" only if you are highly certain given the retrieved text; "medium" or "low" otherwise. Retrieved text is a partial excerpt, not the full judgment — when in doubt, prefer "unclear" and lower confidence over guessing.

Respond with ONLY JSON: {"verdict": "entailed"|"contradicted"|"unclear", "confidence": "high"|"medium"|"low", "reasoning": "one or two sentences"}
"""


def _run_entailment(claimed_content: str, retrieved_text: str) -> dict:
    user_message = f"CLAIM:\n{claimed_content}\n\nRETRIEVED TEXT:\n{retrieved_text[:4000]}"
    last_err = None

    # Throttled to _ENTAILMENT_CONCURRENCY concurrent Groq calls (see module docstring
    # above) -- this is what keeps "parallel" from tripping the free-tier TPM limit.
    with _entailment_semaphore:
        # One retry, same pinned model only (never a smaller cascade model, per S2 brief).
        # On a 429, back off for however long Groq actually says to wait rather than a
        # fixed short delay -- a fixed 1.5s retry into an still-exhausted TPM budget
        # just produces a second failure and a false Mismatch on a correct citation.
        for attempt in range(2):
            try:
                raw = call_groq(ENTAILMENT_SYSTEM_PROMPT, user_message, json_mode=True, model=ENTAILMENT_MODEL)
                data = _parse_json_object(raw)
                # _parse_json_object can return any JSON type (list, string, etc), not
                # just a dict, if the model deviates from the requested shape -- the
                # same crash class fixed in extract_citations for a bare-list response.
                if not isinstance(data, dict):
                    raise ValueError(f"Entailment response was not a JSON object: {raw!r}")
                verdict = data.get("verdict")
                confidence = data.get("confidence")
                if verdict not in ("entailed", "contradicted", "unclear") or confidence not in ("high", "medium", "low"):
                    raise ValueError(f"Malformed entailment response: {raw!r}")
                return {"verdict": verdict, "confidence": confidence, "reasoning": data.get("reasoning", ""), "technical_failure": False}
            except Exception as e:
                last_err = e
                # Full exception (may include upstream API text, billing links, etc.)
                # is logged server-side only -- it must never reach the user-facing
                # reasoning field. An earlier version interpolated str(last_err)
                # directly into "reasoning", which leaked a raw Groq 429 message
                # (including a billing-upsell URL) into the UI as if it were the
                # model's actual analysis of the citation. Caught in UX audit.
                print(f"[CitationVerifier] Entailment attempt {attempt + 1} failed (pinned to {ENTAILMENT_MODEL}): {e}")
                if attempt == 0:
                    match = _RETRY_AFTER_PATTERN.search(str(e))
                    delay = min(float(match.group(1)), 20.0) + 0.5 if match else 1.5
                    time.sleep(delay)

    # technical_failure=True marks this as "we could not run the check" (infra
    # failure -- rate limit, timeout, malformed response), distinct from the
    # model genuinely evaluating the passage and returning "unclear". The
    # citation still maps to Mismatch below (cautious-bias still applies -- a
    # false Verified is worse than an unnecessary flag), but the frontend uses
    # this flag to say "verification incomplete, please retry" rather than
    # presenting it as a confident contradiction finding.
    return {
        "verdict": "unclear",
        "confidence": "low",
        "reasoning": "The verification service was temporarily unavailable and this citation could not be checked. Please retry.",
        "technical_failure": True,
    }


def _paragraph_display(chunk_metadata: dict) -> str:
    numbers = chunk_metadata.get("paragraph_numbers") or []
    if numbers:
        nums = sorted(set(numbers))
        label = f"paragraph {nums[0]}" if len(nums) == 1 else f"paragraphs {nums[0]}–{nums[-1]}"
        return label
    return "paragraph not detected — matched passage shown below"


def verify_citation(citation: dict) -> dict:
    """The full per-citation chain: resolve -> retrieve (case-scoped) -> entailment ->
    cautious-bias three-state mapping. Runs synchronously/blocking; the route layer
    parallelizes N of these across threads."""
    case_name = citation["case_name"]
    citation_string = citation.get("citation_string", "")
    claimed_content = citation.get("claimed_content") or case_name

    case_meta = resolve_case(case_name, citation_string)

    if case_meta is None:
        return {
            "status": "Not found in indexed corpus",
            "matched_case": None,
            "paragraph_display": None,
            "matched_text": None,
            "entailment": None,
            "source_link": None,
        }

    # Layer 1 (primary): retrieve within THIS case only, then run entailment.
    # Deliberately does not depend on paragraph_numbers at all.
    case_hits = search_judgments(claimed_content, top_k=3, case_id_filter=case_meta["case_id"])
    if not case_hits:
        case_hits = search_judgments(case_name, top_k=1, case_id_filter=case_meta["case_id"])

    if not case_hits:
        return {
            "status": "Mismatch",
            "matched_case": case_meta,
            "paragraph_display": None,
            "matched_text": None,
            "entailment": {"verdict": "unclear", "confidence": "low", "reasoning": "Case identified but no retrievable passage found.", "technical_failure": False},
            "source_link": None,
        }

    best_hit = case_hits[0]
    retrieved_text = "\n\n".join(h["text"] for h in case_hits)
    entailment = _run_entailment(claimed_content, retrieved_text)

    # Cautious-bias rule (deterministic, not left to the model): Verified requires
    # entailed AND high confidence. Everything else - contradicted, unclear, or any
    # non-high confidence - defaults to Mismatch. A false Verified is the failure this
    # product exists to prevent; an over-cautious Mismatch is a safe place to be wrong.
    if entailment["verdict"] == "entailed" and entailment["confidence"] == "high":
        status = "Verified"
    else:
        status = "Mismatch"

    # Layer 2 (secondary, display-only): never used above to decide the verdict.
    paragraph_display = _paragraph_display(best_hit["metadata"])

    return {
        "status": status,
        "matched_case": case_meta,
        "paragraph_display": paragraph_display,
        "matched_text": best_hit["text"][:1000],
        "entailment": entailment,
        "source_link": f"/judgments/{case_meta['case_id']}",
    }


async def _verify_indexed(idx: int, citation: dict) -> tuple:
    result = await asyncio.to_thread(verify_citation, citation)
    return idx, citation, result


async def verify_filing_stream(filing_text: str):
    """Public entrypoint: wraps the real generator so any unexpected exception
    yields a clean "error" SSE event instead of silently killing the HTTP
    stream mid-flight (confirmed live: an unhandled AttributeError here left
    the frontend hanging until timeout, with no error shown to the user --
    exactly the "broken state on backend error" class of bug flagged in the
    UX audit)."""
    try:
        async for event in _verify_filing_stream_inner(filing_text):
            yield event
    except Exception as e:
        print(f"[CitationVerifier] verify_filing_stream crashed: {e}")
        yield {
            "type": "error",
            "message": "Something went wrong while verifying this filing. Please try again.",
        }


async def _verify_filing_stream_inner(filing_text: str):
    """Async generator: classify once, then verify all citations concurrently
    (asyncio.to_thread per citation + asyncio.as_completed), yielding an event
    as each one finishes -- not after the slowest one."""
    start = time.perf_counter()
    citations, extraction_incomplete = extract_citations(filing_text)
    total = len(citations)

    yield {
        "type": "citations_found",
        "total": total,
        "citations": [{"case_name": c["case_name"], "citation_string": c["citation_string"]} for c in citations],
        "extraction_incomplete": extraction_incomplete,
    }

    if total == 0:
        yield {
            "type": "done",
            "elapsed_seconds": round(time.perf_counter() - start, 2),
            "report": {
                "citations": [], "extraction_incomplete": extraction_incomplete,
                "summary": {"verified": 0, "mismatch": 0, "not_found": 0, "total": 0}, "coverage_banner": get_coverage_banner(),
            },
        }
        return

    results = [None] * total
    completed = 0
    tasks = [asyncio.ensure_future(_verify_indexed(i, c)) for i, c in enumerate(citations)]

    for fut in asyncio.as_completed(tasks):
        idx, citation, result = await fut
        completed += 1
        merged = {**citation, **result}
        results[idx] = merged
        yield {
            "type": "result",
            "completed": completed,
            "total": total,
            "citation_index": idx,
            "citation": merged,
        }

    summary = {
        "total": total,
        "verified": sum(1 for r in results if r["status"] == "Verified"),
        "mismatch": sum(1 for r in results if r["status"] == "Mismatch"),
        "not_found": sum(1 for r in results if r["status"] == "Not found in indexed corpus"),
        "technical_failures": sum(1 for r in results if (r.get("entailment") or {}).get("technical_failure")),
    }

    yield {
        "type": "done",
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "report": {
            "citations": results,
            "extraction_incomplete": extraction_incomplete,
            "summary": summary,
            "coverage_banner": get_coverage_banner(),
        },
    }
