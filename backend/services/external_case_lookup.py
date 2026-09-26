"""
external_case_lookup.py
=======================
STAGE 1, 2, 8, 9 — External authority lookup, identity resolution, and website content filtering.

Key Principles:
1. IDENTITY FIRST: Only the actual cited judgment may be returned as the authority.
2. RELATED AUTHORITIES SEPARATED: Candidates that merely cite or discuss the authority are
   classified as RELATED_AUTHORITY and never passed to proposition NLI.
3. WEBSITE CONTENT FILTERING (Stage 9): Strip all navigation, ads, premium prompts,
   search boxes, and footer chrome. Only clean judgment body text is retained.
"""

from typing import Any
import hashlib
import os
import re
import time
import unicodedata
import urllib.parse
from difflib import SequenceMatcher

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

IK_API_TOKEN = (os.getenv("IK_API_TOKEN", "") or os.getenv("INDIAN_KANOON_TOKEN", "")).strip()
IK_API_BASE  = "https://api.indiankanoon.org"

_CONNECT_TIMEOUT = 5   # seconds
_READ_TIMEOUT    = 10  # seconds
_TIMEOUT         = (_CONNECT_TIMEOUT, _READ_TIMEOUT)

_IK_SEARCH_URL = "https://indiankanoon.org/search/"
_IK_DOC_URL    = "https://indiankanoon.org/doc/"

# ── Party-name canonicalization map ──────────────────────────────────────────

PARTY_ALIASES: dict[str, str] = {
    "cbi":   "central bureau of investigation",
    "ncb":   "narcotics control bureau",
    "ed":    "enforcement directorate",
    "nia":   "national investigation agency",
    "uoi":   "union of india",
    "bcci":  "board of control for cricket in india",
    "sebi":  "securities and exchange board of india",
    "rbi":   "reserve bank of india",
    "nhai":  "national highways authority of india",
    "rti":   "right to information",
    "nct":   "national capital territory",
    "gnct":  "government of national capital territory",
    "dda":   "delhi development authority",
    "mcd":   "municipal corporation of delhi",
    "lic":   "life insurance corporation of india",
    "bsnl":  "bharat sanchar nigam limited",
    "ongc":  "oil and natural gas corporation",
    "ntpc":  "national thermal power corporation",
    "nhrc":  "national human rights commission",
    "upsc":  "union public service commission",
    "ssc":   "staff selection commission",
    "sfio":  "serious fraud investigation office",
    "pmla":  "prevention of money laundering act",
    "ndps":  "narcotic drugs and psychotropic substances",
    "pocso": "protection of children from sexual offences",
    "sc":    "supreme court",
    "hc":    "high court",
    "hcs":   "high courts",
    "scs":   "supreme court",
}


def canonicalize_party_name(name: str) -> str:
    """Expand known abbreviations in a party name to their full canonical form."""
    if not name:
        return name
    name = unicodedata.normalize("NFC", name)
    tokens = name.split()
    result = []
    for tok in tokens:
        key = re.sub(r"[^a-z0-9]", "", tok.lower())
        result.append(PARTY_ALIASES.get(key, tok))
    return " ".join(result)


def _make_session() -> requests.Session:
    s = requests.Session()
    if IK_API_TOKEN:
        s.headers.update({"Authorization": f"Token {IK_API_TOKEN}"})
    s.headers.update({"User-Agent": "LexSetu-CitationVerifier/1.0 (legal-aid; contact@lexsetu.in)"})
    return s


# ── STAGE 9: Website Content Filtering ───────────────────────────────────────

def extract_clean_judgment_content(html: str) -> dict:
    """Stage 9 — Clean scraping and parsing of legal web pages.
    Removes:
    - navigation menus
    - search boxes
    - login text
    - subscription text / premium banners
    - advertisements
    - footer text
    - website branding
    - 'Skip to main content'
    - 'Premium', 'Download', 'Print', 'Cited by', 'Cites'
    - unrelated page chrome

    Returns:
    {
        'canonical_title': str,
        'court': str,
        'date': str,
        'equivalent_citations': str,
        'full_text': str,
        'paragraphs': list[str],
        'document_hash': str (sha256),
    }
    """
    if not html:
        return {
            "canonical_title": "", "court": "", "date": "",
            "equivalent_citations": "", "full_text": "",
            "paragraphs": [], "document_hash": "",
        }

    # Extract metadata tags before stripping
    title_m = re.search(r"<h2 class=[\"\']doc_title[\"\'][^>]*>(.*?)</h2>", html, re.DOTALL) or \
              re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    raw_title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
    # Strip HTML entities in title
    canonical_title = raw_title.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")

    court_m = re.search(r"<h3 class=[\"\']docsource_main[\"\'][^>]*>(.*?)</h3>", html, re.DOTALL) or \
              re.search(r"<span class=[\"\']docsource[\"\'][^>]*>(.*?)</span>", html, re.DOTALL)
    court = re.sub(r"<[^>]+>", "", court_m.group(1)).strip() if court_m else ""

    # Date extraction from title (e.g. 'on 2 July, 2014')
    date_m = re.search(r"\bon\s+(\d{1,2}\s+[a-zA-Z]+,\s*\d{4})\b", canonical_title, re.I)
    date_str = date_m.group(1) if date_m else ""

    cit_m = re.search(r"<h3 class=[\"\']doc_citations[\"\'][^>]*>(.*?)</h3>", html, re.DOTALL)
    equivalent_citations = re.sub(r"<[^>]+>", "", cit_m.group(1)).strip() if cit_m else ""

    # Scope to judgment container if available
    middle_m = re.search(r"<article class=[\"\']middle_column[\"\'][^>]*>(.*?)</article>", html, re.DOTALL)
    content = middle_m.group(1) if middle_m else html

    # Remove script, style, noscript
    clean = re.sub(r"<(script|style|noscript)[^>]*>.*?</(script|style|noscript)>", " ", content, flags=re.DOTALL | re.IGNORECASE)

    # Remove ads, premium banners, options, chrome
    clean = re.sub(r"<div class=[\"\'](?:ad_doc|premium-banner|doc_options|doc_tools|search_header)[^\"\']*[\"\'][^>]*>.*?</div>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<a class=[\"\']premium-banner[^\"\']*[\"\'][^>]*>.*?</a>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<aside[^>]*>.*?</aside>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<nav[^>]*>.*?</nav>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<header[^>]*>.*?</header>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<footer[^>]*>.*?</footer>", " ", clean, flags=re.DOTALL | re.IGNORECASE)

    # Extract distinct paragraphs from p, blockquote, pre
    blocks = re.findall(r"<(p|blockquote|pre)[^>]*>(.*?)</\1>", clean, re.DOTALL)
    paragraphs = []
    chrome_filter = re.compile(
        r"^(skip to main|upgrade to premium|download|print|get in pdf|take notes|court copy|cites \d+|cited by \d+|user opinions)",
        re.IGNORECASE
    )

    for tag, txt in blocks:
        p = re.sub(r"<[^>]+>", " ", txt)
        p = p.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) < 25:
            continue
        if chrome_filter.search(p):
            continue
        paragraphs.append(p)

    if not paragraphs:
        # Fallback if no <p> tags found
        raw_text = re.sub(r"<[^>]+>", " ", clean)
        raw_text = re.sub(r"\s+", " ", raw_text).strip()
        for chunk in raw_text.split("\n\n"):
            chunk = chunk.strip()
            if len(chunk) > 30 and not chrome_filter.search(chunk):
                paragraphs.append(chunk)

    full_text = "\n\n".join(paragraphs)
    doc_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest() if full_text else ""

    return {
        "canonical_title": canonical_title,
        "court": court,
        "date": date_str,
        "equivalent_citations": equivalent_citations,
        "full_text": full_text,
        "paragraphs": paragraphs,
        "document_hash": doc_hash,
    }


# In-memory cache for external case lookups to avoid repeat calls & rate limits
_EXTERNAL_LOOKUP_CACHE: dict[str, Any] = {}

# ── Search & Candidate Collection ─────────────────────────────────────────────

def _search_indian_kanoon_candidates(session: requests.Session, queries: list[str]) -> tuple[list[dict], bool]:
    """Execute search queries against Indian Kanoon and extract deduplicated candidate records.
    Returns (candidates, had_error).
    """
    seen_ids = set()
    candidates = []
    had_error = False

    for q in queries:
        if not q or not q.strip():
            continue
        try:
            resp = session.get(_IK_SEARCH_URL, params={"formInput": q.strip()}, timeout=_TIMEOUT)
            if resp.status_code == 429:
                print(f"[ExternalLookup] Rate limited (429) for query {q!r}, waiting 1.2s before retry...")
                time.sleep(1.2)
                resp = session.get(_IK_SEARCH_URL, params={"formInput": q.strip()}, timeout=_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"[ExternalLookup] Rate limited or server error ({resp.status_code}) for query {q!r}")
                had_error = True
                continue
            if resp.status_code != 200:
                continue
            articles = re.findall(r"<article class=[\"\']result[\"\'].*?</article>", resp.text, re.DOTALL)
            for art in articles:
                doc_m = re.search(r"/doc/(\d+)/", art)
                doc_id = doc_m.group(1) if doc_m else None
                if not doc_id or doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)

                title_m = re.search(r"<h4 class=[\"\']result_title[\"\']>(.*?)</h4>", art, re.DOTALL)
                title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
                title = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")

                source_m = re.search(r"<span class=[\"\']docsource[\"\']>(.*?)</span>", art)
                court = re.sub(r"<[^>]+>", "", source_m.group(1)).strip() if source_m else ""

                candidates.append({
                    "doc_id": doc_id,
                    "title": title,
                    "court": court,
                    "doc_url": f"{_IK_DOC_URL}{doc_id}/",
                })
        except Exception as e:
            print(f"[ExternalLookup] Search error for query {q!r}: {e}")
            had_error = True
        time.sleep(0.15)  # courteous delay

    return candidates, had_error


# ── Identity Resolution & Related Case Separation ───────────────────────────

class ExternalResolutionResult:
    """Structured result returned by external resolution."""
    __slots__ = (
        "identity_matched", "canonical_case_id", "case_name", "citation",
        "court", "date", "source_url", "document_hash", "clean_text",
        "paragraphs", "resolution_method", "related_authorities", "state", "doc_url"
    )

    def __init__(
        self,
        identity_matched: bool = False,
        canonical_case_id: str = "",
        case_name: str = "",
        citation: str = "",
        court: str = "",
        date: str = "",
        source_url: str = "",
        document_hash: str = "",
        clean_text: str = "",
        paragraphs: list = None,
        resolution_method: str = "",
        related_authorities: list = None,
        state: str = "NOT_FOUND",
        doc_url: str = "",
    ):
        self.identity_matched = identity_matched
        self.canonical_case_id = canonical_case_id
        self.case_name = case_name
        self.citation = citation
        self.court = court
        self.date = date
        self.source_url = source_url
        self.document_hash = document_hash
        self.clean_text = clean_text
        self.paragraphs = paragraphs or []
        self.resolution_method = resolution_method
        self.related_authorities = related_authorities or []
        self.state = state
        self.doc_url = doc_url or source_url

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "identity_matched": self.identity_matched,
            "canonical_case_id": self.canonical_case_id,
            "case_name": self.case_name,
            "citation": self.citation,
            "court": self.court,
            "date": self.date,
            "source_url": self.source_url,
            "document_hash": self.document_hash,
            "doc_url": self.doc_url,
            "resolution_method": self.resolution_method,
            "related_authorities_count": len(self.related_authorities),
        }


def lookup_and_resolve_external_case(
    case_name: str,
    citation_string: str = "",
    context: str = "",
) -> ExternalResolutionResult:
    """STAGE 1, 2, 8, 9 — External authority lookup.

    Searches Indian Kanoon, evaluates candidates against strict identity rules,
    classifies non-matching citing judgments as RELATED_AUTHORITY, and retrieves
    clean text only for the verified authority.
    """
    from services.citation_parser import (
        parse_citation,
        calculate_name_similarity,
        normalize_citation_string,
        normalize_case_name,
    )

    cache_key = f"{normalize_case_name(case_name)}|{normalize_citation_string(citation_string)}"
    if cache_key in _EXTERNAL_LOOKUP_CACHE:
        return _EXTERNAL_LOOKUP_CACHE[cache_key]

    parsed = parse_citation(case_name, citation_string, context)
    session = _make_session()

    # ── Formulate Prioritized Queries ─────────────────────────────────────────
    # 1. Mention/Citation queries: documents returned here actually contain the citation/name
    mention_queries = []
    if citation_string:
        mention_queries.append(f'"{citation_string}"')
    if parsed.get("neutral_citation"):
        mention_queries.append(f'"{parsed["neutral_citation"]}"')
    if case_name:
        mention_queries.append(f'"{case_name}"')

    # 2. Direct Identity queries: target the primary authority itself
    parts = re.split(r"\s+(?:v\.|vs\.?|versus)\s+", case_name, flags=re.IGNORECASE)
    first_party = parts[0].strip() if parts else ""
    identity_queries = []
    if first_party and len(first_party) > 2:
        identity_queries.append(f'title: "{first_party}" doctypes: supremecourt')
        identity_queries.append(f'title: "{first_party}"')
    if case_name:
        identity_queries.append(f'{case_name} doctypes: supremecourt')

    # Run searches
    mention_candidates, err1 = _search_indian_kanoon_candidates(session, mention_queries)
    mention_ids = {c["doc_id"] for c in mention_candidates}
    identity_candidates, err2 = _search_indian_kanoon_candidates(session, identity_queries)
    had_error = err1 or err2

    # Combine candidates preserving priority
    all_candidates = []
    seen_ids = set()
    for c in identity_candidates + mention_candidates:
        if c["doc_id"] not in seen_ids:
            seen_ids.add(c["doc_id"])
            all_candidates.append(c)

    if not all_candidates:
        state = "ERROR" if had_error else ("POSSIBLE_FABRICATION" if citation_string and case_name else "NOT_FOUND")
        res = ExternalResolutionResult(
            identity_matched=False,
            state=state,
        )
        if not had_error:
            _EXTERNAL_LOOKUP_CACHE[cache_key] = res
        return res

    claimed_name = case_name
    claimed_year = parsed.get("year")

    matched_candidate = None
    resolution_method = ""
    related_authorities = []

    for c in all_candidates:
        cand_title = c["title"]
        cand_court = c["court"]
        cand_url   = c["doc_url"]
        cand_id    = c["doc_id"]

        cand_year = None
        y_match = re.search(r"\bon\s+\d{1,2}\s+[a-zA-Z]+,\s*(\d{4})\b", cand_title)
        if y_match:
            cand_year = int(y_match.group(1))

        sim = calculate_name_similarity(claimed_name, cand_title)

        is_name_match = (sim >= 0.65)
        if is_name_match and claimed_year and cand_year and abs(claimed_year - cand_year) > 2:
            is_name_match = False

        if is_name_match and not matched_candidate:
            matched_candidate = c
            resolution_method = "exact_case_name_and_year" if (claimed_year and cand_year == claimed_year) else "normalized_case_name"
        else:
            # Candidate did NOT match identity.
            # STAGE 2: Only classify as RELATED_AUTHORITY if it was retrieved by a
            # citation/phrase search (meaning it actually cites/discusses the claimed authority)
            if cand_id in mention_ids:
                related_authorities.append({
                    "case_name": cand_title,
                    "court": cand_court,
                    "date": str(cand_year) if cand_year else "",
                    "relationship": f"Cites / discusses {claimed_name}",
                    "source_url": cand_url,
                })

    if not matched_candidate:
        # STAGE 7: If authoritative sources were searched and returned no match for the authority,
        # distinguish POSSIBLE_FABRICATION (no authority and no related citations) from UNVERIFIED_CITATION
        state = "POSSIBLE_FABRICATION" if (citation_string and not related_authorities) else "UNVERIFIED_CITATION"
        return ExternalResolutionResult(
            identity_matched=False,
            state=state,
            related_authorities=related_authorities[:8],
        )


    # ── STAGE 3 & 9: Retrieve and clean ONLY the actual cited judgment ─────────
    doc_id = matched_candidate["doc_id"]
    try:
        resp = session.get(f"{_IK_DOC_URL}{doc_id}/", timeout=_TIMEOUT)
        resp.raise_for_status()
        cleaned_doc = extract_clean_judgment_content(resp.text)
    except Exception as e:
        print(f"[ExternalLookup] Failed to fetch full doc {doc_id}: {e}")
        return ExternalResolutionResult(
            identity_matched=False,
            state="ERROR",
            related_authorities=related_authorities[:8],
        )

    res = ExternalResolutionResult(
        identity_matched=True,
        canonical_case_id=f"ik_{doc_id}",
        case_name=cleaned_doc["canonical_title"] or matched_candidate["title"],
        citation=citation_string or cleaned_doc["equivalent_citations"],
        court=cleaned_doc["court"] or matched_candidate["court"] or "Supreme Court of India",
        date=cleaned_doc["date"],
        source_url=f"{_IK_DOC_URL}{doc_id}/",
        document_hash=cleaned_doc["document_hash"],
        clean_text=cleaned_doc["full_text"],
        paragraphs=cleaned_doc["paragraphs"],
        resolution_method=resolution_method,
        related_authorities=related_authorities[:8],
        state="FOUND_AUTHORITY",
    )
    _EXTERNAL_LOOKUP_CACHE[cache_key] = res
    return res


# Backward-compatible wrapper for any existing callers expecting ExternalLookupResult
class ExternalLookupResult:
    __slots__ = ("state", "text", "source", "canonical_title", "doc_url")

    def __init__(self, state: str, text: str = "", source: str = "",
                 canonical_title: str = "", doc_url: str = ""):
        self.state = state
        self.text = text
        self.source = source
        self.canonical_title = canonical_title
        self.doc_url = doc_url

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "source": self.source,
            "canonical_title": self.canonical_title,
            "doc_url": self.doc_url,
        }


def lookup_case_externally(case_name: str, citation_string: str = "") -> ExternalLookupResult:
    """Backward-compatible wrapper mapping new ExternalResolutionResult to legacy shape."""
    res = lookup_and_resolve_external_case(case_name, citation_string)
    if res.identity_matched:
        return ExternalLookupResult(
            state="FOUND",
            text=res.clean_text,
            source="Indian Kanoon",
            canonical_title=res.case_name,
            doc_url=res.source_url,
        )
    if res.state == "ERROR":
        return ExternalLookupResult(state="ERROR", source="Indian Kanoon (network error)")
    return ExternalLookupResult(state="NOT_FOUND")
