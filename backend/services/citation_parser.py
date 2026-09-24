"""
citation_parser.py
==================
STAGE 1 — Citation component parser and normalizer.

Parses every citation into:
- case_name
- citation_string
- year
- court (if available)
- neutral_citation (if available)
- report_abbreviation (SCC, SCR, AIR, SCALE, etc.)
- normalized_citation
- normalized_case_name
"""

import re
import unicodedata
from difflib import SequenceMatcher

from services.external_case_lookup import canonicalize_party_name

_SUFFIX_WORDS = {
    "ors", "anr", "others", "another", "etc", "and", "the", "vs", "versus", "v",
    "thru", "through", "rep", "represented", "by", "its", "state", "govt",
}

# Generic party words that recur across thousands of unrelated cases.
# Overlap on these alone must never be enough to call two citations the same case.
GENERIC_PARTY_WORDS = {
    "state", "union", "india", "government", "govt", "central", "board", "corporation",
    "authority", "commissioner", "secretary", "director", "territory", "nct", "of",
    "municipal", "council", "department", "ministry", "police", "superintendent",
    # State/UT names
    "andhra", "pradesh", "arunachal", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
    "haryana", "himachal", "jharkhand", "karnataka", "kerala", "madhya", "maharashtra",
    "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
    "rajasthan", "sikkim", "tamil", "nadu", "telangana", "tripura", "uttar", "uttarakhand",
    "bengal", "west", "delhi", "andaman", "nicobar", "chandigarh", "dadra", "nagar",
    "haveli", "daman", "diu", "lakshadweep", "puducherry", "jammu", "kashmir", "ladakh",
}

# Known report abbreviations in Indian law
REPORT_ABBREVIATIONS = [
    "SCC", "SCR", "AIR", "SCALE", "CRILJ", "CRI LJ", "DLT", "MLJ", "GLR",
    "ILR", "ALL MR", "BOM CR", "ALT", "ALR", "BLR", "CAL LT",
]


def normalize_citation_string(cit: str) -> str:
    """Normalize a citation string by removing punctuation, collapsing whitespace, and lowercasing."""
    if not cit:
        return ""
    cit = unicodedata.normalize("NFC", cit)
    cit = re.sub(r"[^a-z0-9]", " ", cit.lower())
    return " ".join(cit.split())


def normalize_case_name(name: str) -> str:
    """Normalize a case name for identity comparison.
    1. Canonicalize party abbreviations (CBI -> central bureau of investigation).
    2. Strip date suffixes like 'on 2 July, 2014'.
    3. Strip punctuation and lowercase.
    4. Remove stop words / suffixes.
    """
    if not name:
        return ""
    name = canonicalize_party_name(name)
    # Strip date suffixes in IK titles: 'on 2 July, 2014' or 'on 25 January, 1978'
    name = re.sub(r"\bon\s+\d{1,2}\s+[a-zA-Z]+,\s*\d{4}\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    tokens = [t for t in name.split() if t not in _SUFFIX_WORDS]
    return " ".join(tokens)


def split_parties(name: str) -> tuple[str, str]:
    """Split a case title into (petitioner, respondent)."""
    if not name:
        return "", ""
    name = re.sub(r"\bon\s+\d{1,2}\s+[a-zA-Z]+,\s*\d{4}\b", "", name, flags=re.IGNORECASE)
    parts = re.split(r"\s+(?:v\.|vs\.?|versus)\s+", name, flags=re.IGNORECASE)
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return name.strip(), ""


def calculate_name_similarity(claimed_name: str, candidate_name: str) -> float:
    """Calculate strict identity similarity between two case names.
    STAGE 1:
    1. Overall token similarity and Jaccard.
    2. Bilateral Petitioner and Respondent matching: If a case has both petitioner
       and respondent (e.g. 'Meera Devi v. Union of India'), a candidate with the
       same petitioner but a completely different respondent ('Meera Devi vs State of H.P.')
       MUST be rejected as a different case.
    3. Requires at least one distinctive non-generic token overlap.
    """
    na = normalize_case_name(claimed_name)
    nb = normalize_case_name(candidate_name)
    if not na or not nb:
        return 0.0

    ratio = SequenceMatcher(None, na, nb).ratio()
    set_a, set_b = set(na.split()), set(nb.split())
    jaccard = len(set_a & set_b) / len(set_a | set_b) if (set_a or set_b) else 0.0
    score = max(ratio, jaccard)

    # Require at least one DISTINCTIVE token (not in GENERIC_PARTY_WORDS and len > 3)
    distinctive_overlap = {t for t in (set_a & set_b) if t not in GENERIC_PARTY_WORDS and len(t) > 3}
    if not distinctive_overlap:
        score = min(score, 0.4)

    # Bilateral party check (Petitioner vs Respondent)
    p_claimed, r_claimed = split_parties(claimed_name)
    p_cand, r_cand = split_parties(candidate_name)

    if p_claimed and r_claimed and p_cand and r_cand:
        np_claimed, np_cand = normalize_case_name(p_claimed), normalize_case_name(p_cand)
        nr_claimed, nr_cand = normalize_case_name(r_claimed), normalize_case_name(r_cand)

        sim_p = SequenceMatcher(None, np_claimed, np_cand).ratio()
        sim_r = SequenceMatcher(None, nr_claimed, nr_cand).ratio()

        # If petitioner matches but respondent is completely different (e.g. UOI vs HP) -> penalize heavily
        if sim_p >= 0.70 and sim_r < 0.50:
            score = min(score, 0.35)
        # If respondent matches but petitioner is completely different -> penalize heavily
        elif sim_r >= 0.70 and sim_p < 0.50:
            score = min(score, 0.35)

    return score



def parse_citation(case_name: str, citation_string: str = "", context: str = "") -> dict:
    """Parse citation components per Stage 1 specification.
    Extracts:
    - case_name
    - citation_string
    - year
    - court
    - neutral_citation
    - report_abbreviation
    - normalized_citation
    - normalized_case_name
    """
    combined = f"{case_name} {citation_string} {context}"

    # Year extraction: 4 digits starting with 19 or 20
    year = None
    y_match = re.search(r"\b(19\d\d|20\d\d)\b", citation_string) or re.search(r"\b(19\d\d|20\d\d)\b", case_name)
    if y_match:
        year = int(y_match.group(1))

    # Neutral citation: e.g. 2022 INSC 95, 2024 INSC 123
    neutral = None
    n_match = re.search(r"\b(20\d\d\s+INSC\s+\d+)\b", combined, re.I)
    if n_match:
        neutral = re.sub(r"\s+", " ", n_match.group(1).upper().strip())

    # Court detection
    court = None
    if neutral or re.search(r"\b(supreme\s+court|INSC|SC\b|SCR\b)", combined, re.I):
        court = "Supreme Court of India"
    elif re.search(r"\b(delhi|bombay|madras|calcutta|karnataka|kerala|allahabad|punjab|haryana|gujarat)\s+(high\s+court|hc\b)", combined, re.I):
        court = "High Court"

    # Report abbreviation
    report_abbr = None
    for abbr in REPORT_ABBREVIATIONS:
        if re.search(rf"\b{abbr}\b", citation_string, re.I):
            report_abbr = abbr.upper().replace(" ", "")
            break

    norm_cit = normalize_citation_string(citation_string)
    norm_name = normalize_case_name(case_name)

    return {
        "case_name": case_name.strip(),
        "citation_string": citation_string.strip(),
        "year": year,
        "court": court,
        "neutral_citation": neutral,
        "report_abbreviation": report_abbr,
        "normalized_citation": norm_cit,
        "normalized_case_name": norm_name,
    }
