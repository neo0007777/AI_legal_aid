"""
Statute Map Service
===================
Deterministic, offline mapping between pre- and post-2024 Indian criminal statutes:
  • IPC  ↔  BNS  (Bharatiya Nyaya Sanhita, 2023)
  • CrPC ↔  BNSS (Bharatiya Nagarik Suraksha Sanhita, 2023)

Also validates user-provided section references against known mappings and
determines the correct statute based on case date (pre/post 1 July 2024).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional
import re


BNSS_EFFECTIVE_DATE = date(2024, 7, 1)


@dataclass
class StatuteRef:
    """A validated statutory reference."""
    section: str
    statute: str           # e.g. "BNS", "IPC", "BNSS", "CrPC", "NDPS Act"
    status: str            # "verified" | "mapped" | "unverified" | "ambiguous"
    note: str = ""         # explanation (e.g. "Mapped from IPC 302 → BNS 103")
    original_input: str = ""


# ───────────────────────────────────────────────────────
# Core mapping tables
# ───────────────────────────────────────────────────────

# IPC Section → BNS Section (most commonly used in criminal practice)
IPC_TO_BNS = {
    "302": "103",   # Murder
    "304": "105",   # Culpable homicide not amounting to murder
    "304A": "106",  # Death by negligence
    "304B": "80",   # Dowry death
    "306": "108",   # Abetment of suicide
    "307": "109",   # Attempt to murder
    "323": "115",   # Voluntarily causing hurt
    "324": "118",   # Voluntarily causing hurt by dangerous weapons
    "326": "119",   # Voluntarily causing grievous hurt by dangerous weapons
    "354": "74",    # Assault or criminal force to woman with intent to outrage modesty
    "354A": "75",   # Sexual harassment
    "354B": "76",   # Assault with intent to disrobe
    "354C": "77",   # Voyeurism
    "354D": "78",   # Stalking
    "363": "137",   # Kidnapping
    "365": "140",   # Kidnapping with intent to confine
    "366": "141",   # Kidnapping, abducting a woman to compel marriage
    "375": "63",    # Rape (definition)
    "376": "64",    # Punishment for rape
    "377": "69",    # Unnatural offences (repealed, closest BNS provision)
    "379": "303",   # Theft
    "380": "305",   # Theft in dwelling house
    "384": "308",   # Extortion
    "392": "309",   # Robbery
    "395": "310",   # Dacoity
    "397": "312",   # Robbery or dacoity with attempt to cause death
    "406": "316",   # Criminal breach of trust
    "409": "316",   # CBT by public servant (mapped to same BNS section)
    "411": "317",   # Dishonestly receiving stolen property
    "420": "318",   # Cheating and dishonestly inducing delivery of property
    "427": "324",   # Mischief causing damage
    "429": "325",   # Mischief by killing or maiming animal
    "447": "329",   # Criminal trespass
    "452": "333",   # House-trespass after preparation for hurt
    "467": "336",   # Forgery of valuable security
    "468": "337",   # Forgery for purpose of cheating
    "471": "340",   # Using as genuine a forged document
    "494": "82",    # Marrying again during lifetime of husband or wife
    "498A": "85",   # Husband or relative of husband subjecting woman to cruelty
    "499": "356",   # Defamation
    "500": "356",   # Punishment for defamation
    "504": "351",   # Intentional insult with intent to provoke breach of peace
    "506": "351",   # Criminal intimidation
    "509": "79",    # Word, gesture or act intended to insult modesty of a woman
    "511": "62",    # Punishment for attempting to commit offences
    # Common IPC sections used in bail matters
    "34": "3(5)",   # Common intention
    "109": "48",    # Abetment
    "114": "50",    # Abettor present when offence committed
    "120B": "61",   # Criminal conspiracy
    "147": "189",   # Rioting
    "148": "190",   # Rioting armed with deadly weapon
    "149": "190",   # Unlawful assembly (mapped)
    "153A": "196",  # Promoting enmity between groups
    "186": "221",   # Obstructing public servant in discharge of duty
    "188": "223",   # Disobedience of order by public servant
    "295A": "299",  # Deliberate act to outrage religious feelings
    "341": "126",   # Wrongful restraint
    "342": "127",   # Wrongful confinement
}

# Reverse map: BNS → IPC
BNS_TO_IPC = {v: k for k, v in IPC_TO_BNS.items()}

# CrPC Section → BNSS Section (procedural — bail provisions especially)
CRPC_TO_BNSS = {
    "41":    "35",    # When police may arrest without warrant
    "41A":   "35",    # Notice of appearance before police officer
    "154":   "173",   # Information in cognizable cases (FIR)
    "155":   "174",   # Information as to non-cognizable cases
    "156":   "175",   # Police officer's power to investigate
    "157":   "176",   # Procedure for investigation
    "161":   "180",   # Examination of witnesses by police
    "164":   "183",   # Recording of confessions and statements
    "167":   "187",   # Procedure when investigation cannot be completed in 24 hours
    "167(2)": "187",  # Default bail
    "169":   "189",   # Release of accused when evidence is deficient
    "170":   "190",   # Cases to be sent to Magistrate
    "173":   "193",   # Report of police officer on completion of investigation (chargesheet)
    "190":   "210",   # Cognizance of offences by Magistrates
    "197":   "218",   # Prosecution of Judges and public servants
    "200":   "223",   # Examination of complainant
    "204":   "227",   # Issue of process
    "227":   "250",   # Discharge
    "228":   "251",   # Framing of charge
    "239":   "262",   # Discharge (warrant cases)
    "240":   "263",   # Framing of charge (warrant cases)
    "244":   "267",   # Evidence for prosecution
    "300":   "337",   # Person once convicted or acquitted not to be tried again
    "309":   "346",   # Power to postpone or adjourn proceedings
    "311":   "348",   # Power to summon material witness
    "313":   "351",   # Examination of accused
    "319":   "357",   # Power to proceed against other persons
    "357":   "395",   # Order to pay compensation
    "357A":  "396",   # Victim compensation scheme
    "378":   "419",   # Appeal in case of acquittal
    "389":   "430",   # Suspension of sentence pending appeal
    "397":   "438",   # Calling for records to exercise powers of revision
    "401":   "442",   # High Court's powers of revision
    "436":   "478",   # Bail in bailable offences
    "437":   "480",   # Bail in non-bailable offences (Magistrate)
    "438":   "482",   # Anticipatory bail
    "439":   "483",   # Special powers of High Court or Court of Session regarding bail
    "482":   "528",   # Inherent powers of High Court
}

# Reverse map: BNSS → CrPC
BNSS_TO_CRPC = {v: k for k, v in CRPC_TO_BNSS.items()}


# ───────────────────────────────────────────────────────
# Section number extraction from user text
# ───────────────────────────────────────────────────────

# Matches patterns like "302 IPC", "Section 483 BNSS", "S. 438 CrPC", "420/34 IPC"
_SECTION_PATTERN = re.compile(
    r"(?:(?:Section|Sec\.?|S\.?)\s+)?"             # optional "Section" prefix
    r"(\d{1,4}[A-Z]?)"                              # section number (e.g. 302, 304A, 498A)
    r"(?:\s*/\s*(\d{1,4}[A-Z]?))?"                  # optional slash-separated second section
    r"(?:\s+(?:of\s+(?:the\s+)?)?"                   # optional "of the"
    r"(IPC|BNS|CrPC|Cr\.?P\.?C\.?|BNSS|NDPS|POCSO|IT Act|SC/ST Act|NI Act))?"  # statute name
    , re.IGNORECASE
)

_STATUTE_NORMALIZE = {
    "ipc": "IPC",
    "bns": "BNS",
    "crpc": "CrPC",
    "cr.p.c.": "CrPC",
    "cr.p.c": "CrPC",
    "crp.c.": "CrPC",
    "bnss": "BNSS",
    "ndps": "NDPS Act",
    "pocso": "POCSO Act",
    "it act": "IT Act",
    "sc/st act": "SC/ST Act",
    "ni act": "NI Act",
}


def _normalize_statute(s: str | None) -> str | None:
    if not s:
        return None
    return _STATUTE_NORMALIZE.get(s.lower().strip(), s.strip())


def extract_sections(text: str) -> list[tuple[str, str | None]]:
    """Extract (section_number, statute_name_or_None) pairs from text."""
    results = []
    for m in _SECTION_PATTERN.finditer(text):
        sec1 = m.group(1)
        sec2 = m.group(2)
        statute = _normalize_statute(m.group(3))
        results.append((sec1, statute))
        if sec2:
            results.append((sec2, statute))
    return results


# ───────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────

def validate_section(
    section: str,
    claimed_statute: str | None = None,
    case_date: date | None = None,
) -> StatuteRef:
    """Validate a section reference and map to the correct statute if needed.

    Parameters
    ----------
    section : str
        The section number (e.g. "302", "438", "483").
    claimed_statute : str | None
        The statute the user claims (e.g. "IPC", "BNSS"). May be None.
    case_date : date | None
        The date of the case/offence. Used to determine which statute applies.

    Returns
    -------
    StatuteRef with status:
        - "verified": the section-statute combination is in our mapping and correct for the date
        - "mapped": we found a mapping and applied it (e.g. user said IPC 302, mapped to BNS 103)
        - "unverified": section not in our mapping tables (could be a special act, or just unknown)
        - "ambiguous": section exists in multiple statutes and we can't determine which
    """
    sec = section.strip().upper()
    claimed = _normalize_statute(claimed_statute)
    original = f"Section {sec}" + (f" {claimed}" if claimed else "")

    # Determine if new-law regime applies
    use_new_law = True  # default: post-July 2024
    if case_date and case_date < BNSS_EFFECTIVE_DATE:
        use_new_law = False

    # RULE 4: If no statute was claimed, NEVER infer statute solely from section number.
    if claimed is None:
        possible = []
        if sec in IPC_TO_BNS:
            possible.append(f"IPC (corresponding BNS: {IPC_TO_BNS[sec]})")
        if sec in BNS_TO_IPC:
            possible.append(f"BNS (corresponding IPC: {BNS_TO_IPC[sec]})")
        if sec in CRPC_TO_BNSS:
            possible.append(f"CrPC (corresponding BNSS: {CRPC_TO_BNSS[sec]})")
        if sec in BNSS_TO_CRPC:
            possible.append(f"BNSS (corresponding CrPC: {BNSS_TO_CRPC[sec]})")
        pos_str = f" [Potential candidate: {', '.join(possible)}]" if possible else ""
        return StatuteRef(
            section=sec,
            statute="[STATUTE REQUIRES VERIFICATION]",
            status="unverified",
            note=f"Only section number {sec} provided without statute name.{pos_str} Never infer statute solely from section number. Preserve Section {sec} [STATUTE REQUIRES VERIFICATION].",
            original_input=original,
        )

    # --- Substantive law (IPC / BNS) ---
    if claimed == "IPC" and sec in IPC_TO_BNS:
        bns_sec = IPC_TO_BNS[sec]
        if case_date is not None and case_date >= BNSS_EFFECTIVE_DATE:
            return StatuteRef(
                section=bns_sec, statute="BNS",
                status="mapped",
                note=f"Offence date verified on/after 01-Jul-2024. Mapped IPC {sec} → BNS Section {bns_sec}.",
                original_input=original,
            )
        elif case_date is not None and case_date < BNSS_EFFECTIVE_DATE:
            return StatuteRef(
                section=sec, statute="IPC",
                status="verified",
                note=f"Offence date verified pre-01-Jul-2024. IPC Section {sec} applies.",
                original_input=original,
            )
        else:
            # Date unverified — Rule 4: Do not silently convert an old statutory provision into a new one.
            return StatuteRef(
                section=sec, statute="IPC",
                status="verified",
                note=f"Section {sec} IPC provided. Date of offence not verified — preserve IPC {sec}. (Corresponding BNS: Section {bns_sec} if post-01-Jul-2024 [REQUIRES VERIFICATION OF DATE OF OFFENCE]).",
                original_input=original,
            )

    if claimed == "BNS" and sec in BNS_TO_IPC:
        if case_date is not None and case_date < BNSS_EFFECTIVE_DATE:
            ipc_sec = BNS_TO_IPC[sec]
            return StatuteRef(
                section=ipc_sec, statute="IPC",
                status="mapped",
                note=f"Offence date verified pre-01-Jul-2024. Mapped BNS {sec} → IPC Section {ipc_sec}.",
                original_input=original,
            )
        else:
            return StatuteRef(
                section=sec, statute="BNS",
                status="verified",
                note=f"BNS Section {sec} provided and verified.",
                original_input=original,
            )

    # --- Procedural law (CrPC / BNSS) ---
    if claimed == "CrPC" and sec in CRPC_TO_BNSS:
        bnss_sec = CRPC_TO_BNSS[sec]
        if case_date is not None and case_date >= BNSS_EFFECTIVE_DATE:
            return StatuteRef(
                section=bnss_sec, statute="BNSS",
                status="mapped",
                note=f"Proceeding date verified on/after 01-Jul-2024. Mapped CrPC {sec} → BNSS Section {bnss_sec}.",
                original_input=original,
            )
        elif case_date is not None and case_date < BNSS_EFFECTIVE_DATE:
            return StatuteRef(
                section=sec, statute="CrPC",
                status="verified",
                note=f"Case date verified pre-01-Jul-2024. CrPC Section {sec} applies.",
                original_input=original,
            )
        else:
            # Date unverified — Rule 4: Do not silently convert an old statutory provision into a new one.
            return StatuteRef(
                section=sec, statute="CrPC",
                status="verified",
                note=f"Section {sec} CrPC provided. Proceeding date not verified — preserve CrPC {sec}. (Corresponding BNSS: Section {bnss_sec} if post-01-Jul-2024 [REQUIRES VERIFICATION OF DATE]).",
                original_input=original,
            )

    if claimed == "BNSS" and sec in BNSS_TO_CRPC:
        if case_date is not None and case_date < BNSS_EFFECTIVE_DATE:
            crpc_sec = BNSS_TO_CRPC[sec]
            return StatuteRef(
                section=crpc_sec, statute="CrPC",
                status="mapped",
                note=f"Case date verified pre-01-Jul-2024. Mapped BNSS {sec} → CrPC Section {crpc_sec}.",
                original_input=original,
            )
        else:
            return StatuteRef(
                section=sec, statute="BNSS",
                status="verified",
                note=f"BNSS Section {sec} provided and verified.",
                original_input=original,
            )

    # --- Special Acts or unknown ---
    if claimed and claimed not in ("IPC", "BNS", "CrPC", "BNSS"):
        # NDPS, POCSO, etc. — we don't map these, just pass through
        return StatuteRef(
            section=sec, statute=claimed,
            status="unverified",
            note=f"Section {sec} of {claimed} — not in local mapping tables, requires manual verification",
            original_input=original,
        )

    # No match at all
    return StatuteRef(
        section=sec,
        statute=claimed or "[STATUTE NOT SPECIFIED]",
        status="unverified",
        note=f"Section {sec} not found in IPC/BNS/CrPC/BNSS mapping tables. Verify manually.",
        original_input=original,
    )


def validate_sections_in_text(
    text: str,
    case_date: date | None = None,
) -> list[StatuteRef]:
    """Extract and validate all statutory references found in a text string."""
    extracted = extract_sections(text)
    results = []
    seen = set()
    for sec, statute in extracted:
        key = (sec, statute)
        if key in seen:
            continue
        seen.add(key)
        results.append(validate_section(sec, statute, case_date))
    return results
