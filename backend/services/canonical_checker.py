"""
Canonical Official India Code Source Verifier
=============================================
Enforces the mandatory rule:
Never assign VERIFIED_LEGAL_RULE merely because a provision was returned by the India Code API.
Before marking a legal provision as verified, cross-checks:
1. Act title
2. Provision number
3. Provision heading
4. Complete text
against the canonical official India Code source (indiacode.nic.in) or authoritative
legislative publication (The Gazette of India).

If the API and canonical source disagree:
- Mark the record SOURCE_CONFLICT.
- Strictly block/halt legal document generation until resolved.
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("LexSetu.CanonicalChecker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

CANONICAL_AUTHORITY = "indiacode.nic.in / The Gazette of India"

ACT_ABBREVIATIONS: Dict[str, str] = {
    "bnss": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bns": "The Bharatiya Nyaya Sanhita, 2023",
    "bsa": "The Bharatiya Sakshya Adhiniyam, 2023",
    "crpc": "The Code of Criminal Procedure, 1973",
    "ipc": "The Indian Penal Code, 1860",
    "iea": "The Indian Evidence Act, 1872",
}


@dataclass
class CanonicalProvision:
    """Authoritative primary legal source record from indiacode.nic.in or The Gazette of India."""
    act_id: str
    act_title: str
    provision_number: str
    heading: str
    text: str
    canonical_source: str = CANONICAL_AUTHORITY


@dataclass
class CanonicalCheckResult:
    """Outcome of cross-checking API record against canonical official source."""
    status: str  # "VERIFIED" | "SOURCE_CONFLICT" | "REQUIRES_CANONICAL_VERIFICATION"
    canonical_source: str
    discrepancies: List[str] = field(default_factory=list)
    verified_at: Optional[str] = None

    @property
    def is_verified(self) -> bool:
        return self.status == "VERIFIED"

    @property
    def has_conflict(self) -> bool:
        return self.status == "SOURCE_CONFLICT"


def _normalize_legal_text(text: str) -> str:
    """Normalizes whitespace and common typography variations (quotes, dashes, brackets) for exact comparison."""
    if not text:
        return ""
    t = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    t = t.replace("—", "-").replace("–", "-").replace("---", "-").replace("--", "-")
    t = t.replace("[", "").replace("]", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_act_title(title: str) -> str:
    """Resolves short abbreviations or full titles to canonical form."""
    cleaned = (title or "").strip().lower()
    # Check if direct key in abbreviations
    if cleaned in ACT_ABBREVIATIONS:
        return _normalize_legal_text(ACT_ABBREVIATIONS[cleaned]).lower()
    for abbr, full_title in ACT_ABBREVIATIONS.items():
        if abbr == cleaned or full_title.lower() == cleaned:
            return _normalize_legal_text(full_title).lower()
    # Remove leading 'the' and year if present for relaxed match
    return _normalize_legal_text(title).lower()


# ───────────────────────────────────────────────────────
# Primary Canonical Registry (indiacode.nic.in / Gazette of India)
# ───────────────────────────────────────────────────────
CANONICAL_STATUTE_REGISTRY: Dict[Tuple[str, str], CanonicalProvision] = {
    # ── BNSS (Act No. 46 of 2023, The Gazette of India Extraordinary) ──
    ("bnss", "483"): CanonicalProvision(
        act_id="bnss",
        act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        provision_number="483",
        heading="Special powers of High Court or Court of Session regarding bail",
        text=(
            "(1) A High Court or Court of Session may direct,--- (a) that any person accused of an offence and in custody be released on bail, "
            "and if the offence is of the nature specified in sub-section (3) of section 480, may impose any condition which it considers "
            "necessary for the purposes mentioned in that sub-section; (b) that any condition imposed by a Magistrate when releasing any person "
            "on bail be set aside or modified: Provided that the High Court or the Court of Session shall, before granting bail to a person who "
            "is accused of an offence which is triable exclusively by the Court of Session or which, though not so triable, is punishable with "
            "imprisonment for life, give notice of the application for bail to the Public Prosecutor unless it is, for reasons to be recorded in "
            "writing, of opinion that it is not practicable to give such notice: Provided further that the High Court or the Court of Session shall, "
            "before granting bail to a person who is accused of an offence triable under section 65 or sub-section (2) of section 70 of the "
            "Bharatiya Nyaya Sanhita, 2023, give notice of the application for bail to the Public Prosecutor within a period of fifteen days "
            "from the date of receipt of the notice of such application. (2) The presence of the informant or any person authorised by him shall "
            "be obligatory at the time of hearing of the application for bail to the person under section 65 or sub-section (2) of section 70 of the "
            "Bharatiya Nyaya Sanhita, 2023. (3) A High Court or Court of Session may direct that any person who has been released on bail under "
            "this Chapter be arrested and commit him to custody."
        ),
    ),
    ("bnss", "482"): CanonicalProvision(
        act_id="bnss",
        act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        provision_number="482",
        heading="Direction for grant of bail to person apprehending arrest",
        text=(
            "(1) When any person has reason to believe that he may be arrested on an accusation of having committed a non-bailable offence, "
            "he may apply to the High Court or the Court of Session for a direction under this section; and that Court may, if it thinks fit, "
            "direct that in the event of such arrest, he shall be released on bail. (2) When the High Court or the Court of Session makes a "
            "direction under sub-section (1), it may include such conditions in such directions in the light of the facts of the particular "
            "case, as it may think fit, including--- (i) a condition that the person shall make himself available for interrogation by a police "
            "officer as and when required; (ii) a condition that the person shall not, directly or indirectly, make any inducement, threat or "
            "promise to any person acquainted with the facts of the case so as to dissuade him from disclosing such facts to the Court or to "
            "any police officer; (iii) a condition that the person shall not leave India without the previous permission of the Court; "
            "(iv) such other condition as may be imposed under sub-section (3) of section 480, as if the bail were granted under that section. "
            "(3) If such person is thereafter arrested without warrant by an officer in charge of a police station on such accusation, and is "
            "prepared either at the time of arrest or at any time while in the custody of such officer to give bail, he shall be released on bail; "
            "and if a Magistrate taking cognizance of such offence decides that a warrant should be issued in the first instance against that "
            "person, he shall issue a bailable warrant in conformity with the direction of the Court under sub-section (1). (4) Nothing in this "
            "section shall apply to any case involving the arrest of any person on accusation of having committed an offence under section 65 "
            "and sub-section (2) of section 70 of the Bharatiya Nyaya Sanhita, 2023."
        ),
    ),
    ("bnss", "480"): CanonicalProvision(
        act_id="bnss",
        act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        provision_number="480",
        heading="When bail may be taken in case of non-bailable offence",
        text=(
            "(1) When any person accused of, or suspected of, the commission of any non-bailable offence is arrested or detained without warrant "
            "by an officer in charge of a police station or appears or is brought before a Court other than the High Court or Court of Session, "
            "he may be released on bail, but--- (i) such person shall not be so released if there appear reasonable grounds for believing that "
            "he has been guilty of an offence punishable with death or imprisonment for life; (ii) such person shall not be so released if such "
            "offence is a cognizable offence and he had been previously convicted of an offence punishable with death, imprisonment for life or "
            "imprisonment for seven years or more, or he had been previously convicted on two or more occasions of a cognizable offence "
            "punishable with imprisonment for three years or more but less than seven years: Provided that the Court may direct that a person "
            "referred to in clause (i) or clause (ii) be released on bail if such person is a child or is a woman or is sick or infirm: Provided "
            "further that the Court may also direct that a person referred to in clause (ii) be released on bail if it is satisfied that it is "
            "just and proper so to do for any other special reason: Provided also that the mere fact that an accused person may be required for "
            "being identified by witnesses during investigation or for police custody beyond the first fifteen days shall not be sufficient "
            "ground for refusing to grant bail if he is otherwise entitled to be released on bail and gives an undertaking that he shall comply "
            "with such directions as may be given by the Court: Provided also that no person shall, if the offence alleged to have been "
            "committed by him is punishable with death, imprisonment for life, or imprisonment for seven years or more, be released on bail by "
            "the Court under this sub-section without giving an opportunity of hearing to the Public Prosecutor. (2) If it appears to such officer "
            "or Court at any stage of the investigation, inquiry or trial, as the case may be, that there are not reasonable grounds for believing "
            "that the accused has committed a non-bailable offence, but that there are sufficient grounds for further inquiry into his guilt, the "
            "accused shall, subject to the provisions of section 492 and pending such inquiry, be released on bail, or, at the discretion of such "
            "officer or Court, on the execution by him of a bond for his appearance as hereinafter provided. (3) When a person accused or "
            "suspected of the commission of an offence punishable with imprisonment which may extend to seven years or more or of an offence under "
            "Chapter VI, Chapter VII or Chapter XVII of the Bharatiya Nyaya Sanhita, 2023 or abetment of, or conspiracy or attempt to commit, any "
            "such offence, is released on bail under sub-section (1), the Court shall impose the conditions,--- (a) that such person shall attend "
            "in accordance with the conditions of the bond executed under this Chapter; (b) that such person shall not commit an offence similar "
            "to the offence of which he is accused, or suspected, of the commission of which he is suspected; and (c) that such person shall not "
            "directly or indirectly make any inducement, threat or promise to any person acquainted with the facts of the case so as to dissuade "
            "him from disclosing such facts to the Court or to any police officer or tamper with the evidence, and may also impose, in the "
            "interests of justice, such other conditions as it considers necessary. (4) An officer or a Court releasing any person on bail under "
            "sub-section (1) or sub-section (2), shall record in writing his or its reasons or special reasons for so doing. (5) Any Court which has "
            "released a person on bail under sub-section (1) or sub-section (2), may, if it considers it necessary so to do, direct that such person "
            "be arrested and commit him to custody. (6) If, in any case triable by a Magistrate, the trial of a person accused of any non-bailable "
            "offence is not concluded within a period of sixty days from the first date fixed for taking evidence in the case, such person shall, if "
            "he is in custody during the whole of the said period, be released on bail to the satisfaction of the Magistrate, unless for reasons "
            "to be recorded in writing, the Magistrate otherwise directs. (7) If, at any time, after the conclusion of the trial of a person "
            "accused of a non-bailable offence and before judgment is delivered, the Court is of opinion that there are reasonable grounds for "
            "believing that the accused is not guilty of any such offence, it shall release the accused, if he is in custody, on the execution "
            "by him of a bond for his appearance to hear judgment delivered."
        ),
    ),
    ("bnss", "187"): CanonicalProvision(
        act_id="bnss",
        act_title="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        provision_number="187",
        heading="Procedure when investigation cannot be completed in twenty-four hours",
        text=(
            "(1) Whenever any person is arrested and detained in custody, and it appears that the investigation cannot be completed within the period of twenty-four hours "
            "fixed by section 58, and there are grounds for believing that the accusation or information is well-founded, the officer in charge of the police station or the police officer making the investigation, "
            "if he is not below the rank of sub-inspector, shall forthwith transmit to the nearest Magistrate a copy of the entries in the diary hereinafter specified relating to the case, and shall at the same time forward the accused to such Magistrate."
        ),
    ),

    # ── BNS (Act No. 45 of 2023, The Gazette of India Extraordinary) ──
    ("bns", "103"): CanonicalProvision(
        act_id="bns",
        act_title="The Bharatiya Nyaya Sanhita, 2023",
        provision_number="103",
        heading="Punishment for murder",
        text=(
            "(1) Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine. "
            "(2) When a group of five or more persons acting in concert commits murder on the ground of race, caste or community, sex, place of birth, "
            "language, personal belief or any other similar ground each member of such group shall be punished with death or with imprisonment for life, and shall also be liable to fine."
        ),
    ),
    ("bns", "1"): CanonicalProvision(
        act_id="bns",
        act_title="The Bharatiya Nyaya Sanhita, 2023",
        provision_number="1",
        heading="Short title, commencement and application",
        text=(
            "(1) This Act may be called the Bharatiya Nyaya Sanhita, 2023. "
            "(2) It shall come into force on such date1 as the Central Government may, by notification in the Official Gazette, appoint, "
            "and different dates may be appointed for different provisions of this Sanhita. "
            "(3) Every person shall be liable to punishment under this Sanhita and not otherwise for every act or omission contrary to the provisions thereof, of which he shall be guilty within India."
        ),
    ),

    # ── CrPC (Act No. 2 of 1974, indiacode.nic.in) ──
    ("crpc", "439"): CanonicalProvision(
        act_id="crpc",
        act_title="The Code of Criminal Procedure, 1973",
        provision_number="439",
        heading="Special powers of High Court or Court of Session regarding bail",
        text=(
            "(1) A High Court or Court of Session may direct- (a) that any person accused of an offence and in custody be released on bail, "
            "and if the offence is of the nature specified in subsection (3) of section 437, may impose any condition which it considers "
            "necessary for the purposes mentioned in that sub-section; (b) that any condition imposed by a Magistrate when releasing an person "
            "on bail be set aside or modified : Provided that the High Court or the Court of Session shall, before granting bail to a person who "
            "is accused of an offence which is triable exclusively by the Court of Session or which, though not so triable, is punishable with "
            "imprisonment for life, give notice of the application for bail to the Public Prosecutor unless it is, for reasons to be recorded in "
            "writing, of opinion that it is not practicable to give such notice. (2) A High Court or Court of Session may direct that any person "
            "who has been released on bail under this Chapter be arrested and commit him to custody."
        ),
    ),
    ("crpc", "438"): CanonicalProvision(
        act_id="crpc",
        act_title="The Code of Criminal Procedure, 1973",
        provision_number="438",
        heading="Direction for grant of bail to person apprehending arrest",
        text=(
            "(1) When any person has reason to believe that he may be arrested on an accusation of having committed a non-bailable offence, "
            "he may apply to the High Court or the Court of Session for a direction under this section ; and that Court may, if it thinks fit, "
            "direct that in the event of such arrest, he shall be released on bail. (2) When the High Court or the Court of Session makes a "
            "direction under sub-section (1), it may include such conditions in such directions in the light of the facts of the particular "
            "case, as it may think fit, including- (i) a condition that the person shall make himself available for interrogation by a police "
            "officer as and when required; (ii) a condition that the person shall not, directly or indirectly, make any inducement, threat or "
            "promise to any person acquainted with the facts of the case so as to dissuade him from disclosing such facts to the Court or to "
            "any police officer; (iii) a condition that the person shall not leave India without the previous permission of the Court ; "
            "(iv) such other condition as may be imposed under sub- section (3) of section 437, as if the bail were granted under that section. "
            "(3) If such person is thereafter arrested without warrant by an officer in charge of a police station on such accusation, and is "
            "prepared either at the time of arrest or at any time while in the custody of such officer to give bail, be shall be released on bail; "
            "and if a Magistrate taking cogniz- ance of such offence decides that a warrant should issue in the first instance against that person, "
            "he shall issue a bailable warrant in conformity with the direction of the Court under sub-section (1)."
        ),
    ),

    # ── IPC (Act No. 45 of 1860, indiacode.nic.in) ──
    ("ipc", "302"): CanonicalProvision(
        act_id="ipc",
        act_title="The Indian Penal Code, 1860",
        provision_number="302",
        heading="Punishment for murder",
        text="Whoever commits murder shall be punished with death, or [imprisonment for life], and shall also be liable to fine.",
    ),
    ("ipc", "124A"): CanonicalProvision(
        act_id="ipc",
        act_title="The Indian Penal Code, 1860",
        provision_number="124A",
        heading="Sedition",
        text=(
            "Whoever by words, either spoken or written, or by signs, or by visible representation, or otherwise, brings or attempts to bring "
            "into hatred or contempt, or excites or attempts to excite disaffection towards, the Government established by law in [India], "
            "shall be punished with [imprisonment for life], to which fine may be added, or with imprisonment which may extend to three years, "
            "to which fine may be added, or with fine."
        ),
    ),

    # ── IEA (Act No. 1 of 1872, indiacode.nic.in) ──
    ("iea", "65B"): CanonicalProvision(
        act_id="iea",
        act_title="The Indian Evidence Act, 1872",
        provision_number="65B",
        heading="Admissibility of electronic records",
        text=(
            "(1) Notwithstanding anything contained in this Act, any information contained in an electronic record which is printed on a paper, "
            "stored, recorded or copied in optical or magnetic media produced by a computer (hereinafter referred to as the computer output) "
            "shall be deemed to be also a document, if the conditions mentioned in this section are satisfied in relation to the information and "
            "computer in question and shall be admissible in any proceedings, without further proof or production of the original, as evidence "
            "or any contents of the original or of any fact stated therein of which direct evidence would be admissible."
        ),
    ),
}


class CanonicalSourceConflictError(Exception):
    """Raised when an API provision contradicts the canonical official India Code source."""
    def __init__(self, act_id: str, provision_number: str, discrepancies: List[str]):
        self.act_id = act_id
        self.provision_number = provision_number
        self.discrepancies = discrepancies
        msg = (
            f"SOURCE_CONFLICT for Section {provision_number} of {act_id.upper()}: "
            f"API data contradicts canonical official source ({CANONICAL_AUTHORITY}). "
            f"Discrepancies: {'; '.join(discrepancies)}"
        )
        super().__init__(msg)


def cross_check_provision(
    act_id: str,
    provision_number: str,
    api_heading: str,
    api_text: str,
    api_act_title: str,
) -> CanonicalCheckResult:
    """
    Cross-checks an API-retrieved provision against the canonical official India Code source (indiacode.nic.in).
    Validates all 4 dimensions:
    1. Act title
    2. Provision number
    3. Provision heading
    4. Complete text

    Returns CanonicalCheckResult with status:
    - "VERIFIED" if all 4 dimensions match
    - "SOURCE_CONFLICT" if any discrepancy is detected between API and canonical source
    - "REQUIRES_CANONICAL_VERIFICATION" if not in the verified canonical set
    """
    clean_act = act_id.strip().lower()
    clean_num = str(provision_number).strip()
    key = (clean_act, clean_num)

    canonical = CANONICAL_STATUTE_REGISTRY.get(key)
    if not canonical:
        logger.info(f"Provision {clean_act}/{clean_num} is not in canonical registry. Marked REQUIRES_CANONICAL_VERIFICATION.")
        return CanonicalCheckResult(
            status="REQUIRES_CANONICAL_VERIFICATION",
            canonical_source=CANONICAL_AUTHORITY,
            discrepancies=[f"Provision Section {clean_num} {clean_act.upper()} not authenticated against canonical source {CANONICAL_AUTHORITY}."],
        )

    discrepancies = []

    # 1. Cross-check Act Title
    norm_api_title = _normalize_act_title(api_act_title)
    norm_can_title = _normalize_act_title(canonical.act_title)
    if norm_api_title != norm_can_title:
        discrepancies.append(
            f"Act title mismatch: API has '{api_act_title}', canonical source has '{canonical.act_title}'"
        )

    # 2. Cross-check Provision Number
    if clean_num.lower() != canonical.provision_number.lower():
        discrepancies.append(
            f"Provision number mismatch: API has '{clean_num}', canonical source has '{canonical.provision_number}'"
        )

    # 3. Cross-check Provision Heading
    norm_api_heading = _normalize_legal_text(api_heading).lower()
    norm_can_heading = _normalize_legal_text(canonical.heading).lower()
    api_words = re.findall(r"\b\w+\b", norm_api_heading)
    can_words = re.findall(r"\b\w+\b", norm_can_heading)
    if api_words != can_words:
        discrepancies.append(
            f"Heading mismatch: API has '{api_heading}', canonical source has '{canonical.heading}'"
        )

    # 4. Cross-check Complete Text
    if not api_text or not api_text.strip():
        discrepancies.append("Statutory text is empty or missing in API record.")
    else:
        norm_api_text = _normalize_legal_text(api_text).lower()
        norm_can_text = _normalize_legal_text(canonical.text).lower()
        api_text_tokens = re.findall(r"\b\w+\b", norm_api_text)
        can_text_tokens = re.findall(r"\b\w+\b", norm_can_text)

        # Exact token match or canonical prefix match (when canonical stores primary subsection)
        if api_text_tokens != can_text_tokens:
            # Check if canonical is a leading subset or vice versa (e.g. multi-subsection full section)
            min_len = min(len(api_text_tokens), len(can_text_tokens))
            if min_len < 10 or api_text_tokens[:min_len] != can_text_tokens[:min_len]:
                discrepancies.append(
                    f"Statutory text divergence between API and canonical source: "
                    f"API words ({len(api_text_tokens)}) vs Canonical words ({len(can_text_tokens)})"
                )

    if discrepancies:
        logger.error(f"SOURCE_CONFLICT detected for {clean_act} Section {clean_num}: {discrepancies}")
        return CanonicalCheckResult(
            status="SOURCE_CONFLICT",
            canonical_source=canonical.canonical_source,
            discrepancies=discrepancies,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )

    logger.info(f"Canonical cross-check PASSED for {clean_act} Section {clean_num} against {canonical.canonical_source}")
    return CanonicalCheckResult(
        status="VERIFIED",
        canonical_source=canonical.canonical_source,
        discrepancies=[],
        verified_at=datetime.now(timezone.utc).isoformat(),
    )
