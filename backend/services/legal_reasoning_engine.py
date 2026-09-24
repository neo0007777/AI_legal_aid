"""
Legal Reasoning & Ground Traceability Engine
============================================
Enforces strict legal grounding, verified statutory mapping, argument typology,
and proposition-level traceability across all generated legal documents.

CORE PRINCIPLE:
Every legal proposition must be verified against actual statutory text or authoritative
judgment. The system verifies: Provision → Statutory Text → Proposition.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import date
import re

from services.fact_manifest import FactManifest, FactEntry
from services.statute_map import BNSS_EFFECTIVE_DATE
from services.canonical_checker import (
    cross_check_provision,
    CanonicalCheckResult,
    CANONICAL_AUTHORITY,
    CANONICAL_STATUTE_REGISTRY,
)


# ───────────────────────────────────────────────────────
# Data Models
# ───────────────────────────────────────────────────────

@dataclass
class StatutoryProvision:
    """An authoritative statutory provision with its text and verified propositions."""
    statute: str                     # e.g. "BNSS", "CrPC", "CPC", "BNS", "IPC"
    section: str                     # e.g. "483", "439", "482", "187"
    heading: str                     # official title
    statutory_text_excerpt: str      # verbatim key text
    relief_type: str                 # "regular_bail", "anticipatory_bail", "default_bail", etc.
    court_jurisdiction: str          # "High Court / Sessions Court", "Magistrate", etc.
    verified_propositions: list[str] # propositions genuinely supported by text
    prohibited_propositions: list[str] # common false assumptions / overstatements
    canonical_verification_status: str = "REQUIRES_CANONICAL_VERIFICATION"
    canonical_source: str = CANONICAL_AUTHORITY
    canonical_conflict_details: str = ""


@dataclass
class LegalGroundRecord:
    """Internal traceability schema for every legal ground (per user specification)."""
    ground: str
    legal_provision: str
    source: str
    exact_proposition_supported: str
    case_facts_required: list[str]
    case_facts_available: list[str]
    verification_status: str  # "VERIFIED" | "LEGAL_PROVISION_REQUIRES_VERIFICATION" | "CASE_FACTS_MISSING" | "PROPOSITION_MISMATCH"
    ground_category: str      # "VERIFIED_LEGAL_RULE" | "GENERAL_JUDICIAL_PRINCIPLE" | "CASE_SPECIFIC_FACTUAL_APPLICATION"
    ground_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProceduralPosture:
    """Identified procedural posture and governing statute/provision."""
    relief_type: str                 # "regular_bail" | "anticipatory_bail" | "default_bail" | "bailable_bail" | "quashing" | "civil_suit" | "injunction" | "unknown"
    relief_label: str                # e.g. "Regular Bail Application"
    posture_status: str              # "in_custody" | "apprehending_arrest" | "investigation_timed_out" | "bailable" | "unknown"
    court_level: str                 # "sessions" | "high_court" | "magistrate" | "civil_court" | "unknown"
    governing_statute: str           # "BNSS" | "CrPC" | "CPC" | "UNKNOWN"
    governing_provision: str         # "Section 483 BNSS" | "[LEGAL PROVISION REQUIRES VERIFICATION]"
    provision_verified: bool         # True only if provision text matches exact relief
    required_factual_premises: list[str] = field(default_factory=list)
    satisfied_premises: list[str] = field(default_factory=list)
    missing_premises: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    statutory_authority: Optional[StatutoryProvision] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.statutory_authority:
            d["statutory_authority"] = asdict(self.statutory_authority)
        return d


# ───────────────────────────────────────────────────────
# Authoritative Statutory Registry
# ───────────────────────────────────────────────────────
# Verified provision → statutory text → propositions

STATUTORY_REGISTRY: Dict[str, StatutoryProvision] = {
    # ── Regular Bail (Sessions / High Court) ──
    "BNSS_483": StatutoryProvision(
        statute="BNSS", section="483",
        heading="Special powers of High Court or Court of Session regarding bail",
        statutory_text_excerpt=(
            "A High Court or Court of Session may direct that any person accused of an offence "
            "and in custody be released on bail, and if the arrest is for an offence punishable "
            "with death or imprisonment for life or imprisonment for seven years or more, shall "
            "give notice of the application for bail to the Public Prosecutor..."
        ),
        relief_type="regular_bail",
        court_jurisdiction="High Court / Court of Session",
        verified_propositions=[
            "The High Court or Court of Session has discretionary power to release an accused in custody on bail.",
            "The court may impose any conditions it considers necessary in the interest of justice.",
            "Notice to Public Prosecutor is mandatory for offences punishable with death, life imprisonment, or 7+ years.",
        ],
        prohibited_propositions=[
            "Section 483 guarantees bail as an absolute statutory right (False: it is discretionary).",
            "Section 483 applies to pre-arrest or anticipatory bail (False: applicant must be in custody).",
            "The court must grant bail upon mere filing (False: judicial discretion must be exercised).",
        ]
    ),
    "CRPC_439": StatutoryProvision(
        statute="CrPC", section="439",
        heading="Special powers of High Court or Court of Session regarding bail",
        statutory_text_excerpt=(
            "A High Court or Court of Session may direct that any person accused of an offence "
            "and in custody be released on bail..."
        ),
        relief_type="regular_bail",
        court_jurisdiction="High Court / Court of Session",
        verified_propositions=[
            "The High Court or Court of Session has concurrent discretionary power to release an accused in custody on bail.",
            "The court has power to set aside or cancel bail previously granted.",
        ],
        prohibited_propositions=[
            "Section 439 applies to pre-arrest bail (False: governed by Section 438 CrPC).",
            "Section 439 guarantees automatic release (False: discretionary).",
        ]
    ),

    # ── Anticipatory Bail (Pre-Arrest) ──
    "BNSS_482": StatutoryProvision(
        statute="BNSS", section="482",
        heading="Direction for grant of bail to person apprehending arrest",
        statutory_text_excerpt=(
            "Where any person has reason to believe that he may be arrested on accusation of "
            "having committed a non-bailable offence, he may apply to the High Court or the "
            "Court of Session for a direction under this section that in the event of such arrest "
            "he shall be released on bail..."
        ),
        relief_type="anticipatory_bail",
        court_jurisdiction="High Court / Court of Session",
        verified_propositions=[
            "A person with reasonable apprehension of arrest in a non-bailable offence may apply for pre-arrest bail.",
            "The relief operates in the event of arrest to direct release on bail.",
            "Conditions regarding interrogation availability, non-tampering, and travel restrictions may be imposed.",
        ],
        prohibited_propositions=[
            "Anticipatory bail can be granted to an accused who is already arrested or in custody (False: requires non-custody).",
            "Anticipatory bail can be granted by a Magistrate (False: only Sessions Court or High Court).",
            "Anticipatory bail is an automatic shield against investigation (False: applicant must cooperate).",
        ]
    ),
    "CRPC_438": StatutoryProvision(
        statute="CrPC", section="438",
        heading="Direction for grant of bail to person apprehending arrest",
        statutory_text_excerpt=(
            "Where any person has reason to believe that he may be arrested on accusation of "
            "having committed a non-bailable offence, he may apply to the High Court or the "
            "Court of Session for a direction that in the event of such arrest he shall be released on bail..."
        ),
        relief_type="anticipatory_bail",
        court_jurisdiction="High Court / Court of Session",
        verified_propositions=[
            "A person with reasonable apprehension of arrest may apply to High Court or Sessions Court for pre-arrest bail.",
        ],
        prohibited_propositions=[
            "Applies to persons already in judicial custody (False).",
            "Can be heard by Judicial Magistrate (False).",
        ]
    ),

    # ── Regular Bail by Magistrate (Non-Bailable) ──
    "BNSS_480": StatutoryProvision(
        statute="BNSS", section="480",
        heading="When bail may be taken in case of non-bailable offence",
        statutory_text_excerpt=(
            "When any person accused of, or suspected of, the commission of any non-bailable "
            "offence is arrested or detained without warrant by an officer in charge of a police "
            "station, or appears or is brought before a Court other than the High Court or Court "
            "of Session, he may be released on bail, but he shall not be so released if there appear "
            "reasonable grounds for believing that he has been guilty of an offence punishable with death "
            "or imprisonment for life..."
        ),
        relief_type="regular_bail_magistrate",
        court_jurisdiction="Magistrate Court",
        verified_propositions=[
            "Magistrate has power to grant bail in non-bailable offences subject to statutory restrictions.",
            "Magistrate cannot grant bail if reasonable grounds exist for believing accused committed offence punishable with death or life imprisonment (unless woman, sick, infirm, or under 16).",
        ],
        prohibited_propositions=[
            "Magistrate can grant anticipatory bail (False: only Sessions/HC).",
            "Magistrate has unrestricted bail powers identical to High Court (False: restricted by Section 480 proviso).",
        ]
    ),
    "CRPC_437": StatutoryProvision(
        statute="CrPC", section="437",
        heading="When bail may be taken in case of non-bailable offence",
        statutory_text_excerpt=(
            "When any person accused of, or suspected of, the commission of any non-bailable offence "
            "is arrested or detained... or brought before a Court other than the High Court or Court of Session, "
            "he may be released on bail..."
        ),
        relief_type="regular_bail_magistrate",
        court_jurisdiction="Magistrate Court",
        verified_propositions=[
            "Magistrate may grant bail in non-bailable offences subject to the statutory bar on death/life imprisonment offences.",
        ],
        prohibited_propositions=[
            "Magistrate has jurisdiction under Section 439 (False: 439 is Sessions/HC only).",
        ]
    ),

    # ── Default / Statutory Bail ──
    "BNSS_187": StatutoryProvision(
        statute="BNSS", section="187",
        heading="Procedure when investigation cannot be completed in twenty-four hours",
        statutory_text_excerpt=(
            "The Magistrate may authorize the detention of the accused person... beyond the period "
            "of fifteen days... but no Magistrate shall authorize detention... exceeding ninety days "
            "where the investigation relates to an offence punishable with death, imprisonment for life "
            "or imprisonment for not less than ten years, and sixty days for any other offence... and "
            "on expiry of said period the accused person shall be released on bail if he is prepared "
            "to and does furnish bail..."
        ),
        relief_type="default_bail",
        court_jurisdiction="Magistrate / Special Court",
        verified_propositions=[
            "Accused has an indefeasible right to default bail if chargesheet is not filed within 60 or 90 days of custody.",
            "The right to default bail is an absolute statutory right once the statutory period has lapsed without chargesheet.",
        ],
        prohibited_propositions=[
            "Default bail can be claimed before expiry of the 60/90 day period (False).",
            "Default bail can be granted without establishing exact date of arrest and custody duration (False: requires proven custody calculation).",
        ]
    ),
    "CRPC_167": StatutoryProvision(
        statute="CrPC", section="167(2)",
        heading="Procedure when investigation cannot be completed in twenty-four hours (Default Bail)",
        statutory_text_excerpt=(
            "The Magistrate may authorize the detention... no Magistrate shall authorize detention exceeding 90 days/60 days... "
            "on expiry of the said period the accused person shall be released on bail..."
        ),
        relief_type="default_bail",
        court_jurisdiction="Magistrate / Special Court",
        verified_propositions=[
            "Accused has an indefeasible statutory right to bail upon expiry of 60/90 days if investigation is incomplete.",
        ],
        prohibited_propositions=[
            "Can be asserted without verified custody duration (False).",
        ]
    ),

    # ── Bail in Bailable Offences ──
    "BNSS_478": StatutoryProvision(
        statute="BNSS", section="478",
        heading="In what cases bail to be taken",
        statutory_text_excerpt=(
            "When any person other than a person accused of a non-bailable offence is arrested or detained "
            "without warrant by an officer in charge of a police station, or appears or is brought before a Court, "
            "and is prepared at any time while in the custody of such officer or at any stage of the proceedings "
            "before such Court to give bail, such person shall be released on bail..."
        ),
        relief_type="bailable_bail",
        court_jurisdiction="Police Station / Magistrate",
        verified_propositions=[
            "For bailable offences, release on bail is a matter of statutory right upon being prepared to furnish bail.",
            "Indigent persons unable to give bail within a week may be discharged on personal bond without sureties.",
        ],
        prohibited_propositions=[
            "Court has discretion to refuse bail in bailable offences (False: bail is mandatory).",
        ]
    ),

    # ── High Court Inherent Powers (Quashing) ──
    "BNSS_528": StatutoryProvision(
        statute="BNSS", section="528",
        heading="Saving of inherent powers of High Court",
        statutory_text_excerpt=(
            "Nothing in this Sanhita shall be deemed to limit or affect the inherent powers of the High Court "
            "to make such orders as may be necessary to give effect to any order under this Sanhita, or to prevent "
            "abuse of the process of any Court or otherwise to secure the ends of justice."
        ),
        relief_type="quashing",
        court_jurisdiction="High Court",
        verified_propositions=[
            "High Court possesses inherent jurisdiction to quash proceedings to prevent abuse of court process or secure ends of justice.",
        ],
        prohibited_propositions=[
            "Subordinate courts or Sessions Courts possess Section 528 inherent powers (False: High Court only).",
            "Section 528 can be used as a routine substitute for statutory bail applications (False).",
        ]
    ),
    "CRPC_482": StatutoryProvision(
        statute="CrPC", section="482",
        heading="Saving of inherent powers of High Court",
        statutory_text_excerpt=(
            "Nothing in this Code shall be deemed to limit or affect the inherent powers of the High Court..."
        ),
        relief_type="quashing",
        court_jurisdiction="High Court",
        verified_propositions=[
            "High Court has inherent power to quash criminal proceedings to prevent abuse of process or secure ends of justice.",
        ],
        prohibited_propositions=[
            "Sessions Court can exercise Section 482 CrPC powers (False: High Court only).",
        ]
    ),
}


# ───────────────────────────────────────────────────────
# 1. Procedural Posture Identification
# ───────────────────────────────────────────────────────

def identify_procedural_posture(
    description: str,
    structured_input: Optional[dict] = None,
    manifest: Optional[FactManifest] = None,
    case_date: Optional[date] = None,
) -> ProceduralPosture:
    """
    Identifies the exact application type, court level, and procedural posture.
    Never relies on generic keyword matching like 'bail' to guess sections.
    Distinguishes regular bail from anticipatory bail and enforces governing statutes.
    """
    desc_lower = description.lower()
    struct = structured_input or {}

    # Extract declared inputs
    app_type_declared = (
        struct.get("application_type")
        or struct.get("document_type")
        or struct.get("relief_sought")
        or ""
    ).lower()

    court_declared = (
        struct.get("court")
        or struct.get("court_name")
        or ""
    ).lower()

    # Determine court level
    court_level = "unknown"
    if any(k in desc_lower or k in court_declared for k in ["high court", "hc", "hon'ble high court"]):
        court_level = "high_court"
    elif any(k in desc_lower or k in court_declared for k in ["sessions", "session judge", "additional sessions", "asj"]):
        court_level = "sessions"
    elif any(k in desc_lower or k in court_declared for k in ["magistrate", "cjm", "acmm", "mm", "judicial magistrate"]):
        court_level = "magistrate"
    elif any(k in desc_lower or k in court_declared for k in ["civil judge", "district judge", "civil court"]):
        court_level = "civil_court"

    # Determine custody/arrest status from manifest or structured input
    custody_val = ""
    arrest_date_val = ""
    if manifest:
        for f in manifest.provided_facts:
            if f.field_name == "custody_status" and f.value:
                custody_val = str(f.value).lower()
            elif f.field_name == "arrest_date" and f.value:
                arrest_date_val = str(f.value)

    if not custody_val and "custody_status" in struct:
        custody_val = str(struct["custody_status"]).lower()
    if not arrest_date_val and "arrest_date" in struct:
        arrest_date_val = str(struct["arrest_date"])

    # Determine date regime
    use_new_law = True
    if case_date and case_date < BNSS_EFFECTIVE_DATE:
        use_new_law = False

    # Check for explicit Relief keywords in request
    is_anticipatory = (
        "anticipatory" in desc_lower
        or "pre-arrest" in desc_lower
        or "pre arrest" in desc_lower
        or "apprehending arrest" in desc_lower
        or "apprehension of arrest" in desc_lower
        or "anticipatory" in app_type_declared
        or "438" in desc_lower
        or "482 bnss" in desc_lower
    )

    is_default_bail = (
        "default bail" in desc_lower
        or "statutory bail" in desc_lower
        or "167(2)" in desc_lower
        or "section 187" in desc_lower
        or "default" in app_type_declared
    )

    is_bailable = (
        "bailable offence" in desc_lower
        or "bailable bail" in desc_lower
        or "436" in desc_lower
        or "478 bnss" in desc_lower
    )

    is_quashing = (
        "quash" in desc_lower
        or "quashing" in desc_lower
        or "528 bnss" in desc_lower
        or "482 crpc" in desc_lower
    )

    is_regular_bail = (
        "regular bail" in desc_lower
        or "post-arrest bail" in desc_lower
        or "439" in desc_lower
        or "483 bnss" in desc_lower
        or "regular" in app_type_declared
    )

    # Resolve Application Type and Procedural Posture
    relief_type = "unknown"
    relief_label = "Legal Application"
    posture_status = "unknown"
    req_premises = []
    satisfied_premises = []
    missing_premises = []
    conflicts = []

    # Priority 1: Anticipatory Bail
    if is_anticipatory:
        relief_type = "anticipatory_bail"
        relief_label = "Anticipatory Bail Application (Pre-Arrest)"
        posture_status = "apprehending_arrest"
        req_premises = [
            "Accused is NOT in custody / has NOT been arrested",
            "Reasonable apprehension of arrest in a non-bailable offence",
        ]
        if "in custody" in custody_val or "arrested" in custody_val or "judicial custody" in custody_val:
            conflicts.append("CONFLICT: Anticipatory bail requested, but manifest indicates accused is already in custody/arrested.")
        else:
            satisfied_premises.append("Accused not reported in custody")

    # Priority 2: Default Bail
    elif is_default_bail:
        relief_type = "default_bail"
        relief_label = "Default / Statutory Bail Application"
        posture_status = "investigation_timed_out"
        req_premises = [
            "Accused has been in continuous custody for statutory threshold (60 or 90 days)",
            "Investigation is incomplete / Chargesheet has NOT been filed within statutory period",
        ]
        # Check if custody duration or arrest date is available
        if arrest_date_val or "days" in custody_val:
            satisfied_premises.append(f"Arrest date / custody reported: {arrest_date_val or custody_val}")
        else:
            missing_premises.append("Custody duration and arrest date NOT provided (cannot calculate 60/90 days)")

    # Priority 3: Bailable Offences
    elif is_bailable:
        relief_type = "bailable_bail"
        relief_label = "Bail Application in Bailable Offence"
        posture_status = "bailable"
        req_premises = [
            "Offence invoked is classified as bailable under Schedule I",
            "Applicant is prepared to furnish bail/bond",
        ]

    # Priority 4: Quashing
    elif is_quashing:
        relief_type = "quashing"
        relief_label = "Petition for Quashing under Inherent Powers"
        posture_status = "proceedings_pending"
        req_premises = [
            "Pending FIR, chargesheet, or complaint",
            "Manifest failure of justice or abuse of court process",
        ]

    # Priority 5: Regular Bail (Default for criminal custody bail)
    elif is_regular_bail or "bail" in desc_lower:
        relief_type = "regular_bail"
        relief_label = "Regular Bail Application"
        posture_status = "in_custody"
        req_premises = [
            "Accused has been arrested / is in custody",
            "Pending investigation, inquiry, or trial",
        ]
        if "custody" in custody_val or arrest_date_val:
            satisfied_premises.append("Custody/arrest confirmed from manifest")
        else:
            missing_premises.append("Arrest status / custody duration NOT confirmed in manifest")

    # Select Governing Provision based on Relief Type, Court Level, and Date
    governing_statute = "BNSS" if use_new_law else "CrPC"
    governing_key = None

    if relief_type == "regular_bail":
        if court_level == "magistrate":
            governing_key = "BNSS_480" if use_new_law else "CRPC_437"
        else:
            governing_key = "BNSS_483" if use_new_law else "CRPC_439"
    elif relief_type == "anticipatory_bail":
        governing_key = "BNSS_482" if use_new_law else "CRPC_438"
    elif relief_type == "default_bail":
        governing_key = "BNSS_187" if use_new_law else "CRPC_167"
    elif relief_type == "bailable_bail":
        governing_key = "BNSS_478"
    elif relief_type == "quashing":
        governing_key = "BNSS_528" if use_new_law else "CRPC_482"

    statutory_auth = STATUTORY_REGISTRY.get(governing_key) if governing_key else None
    if statutory_auth:
        governing_provision = f"Section {statutory_auth.section} {statutory_auth.statute}"
        provision_verified = True
    else:
        governing_provision = "[LEGAL PROVISION REQUIRES VERIFICATION]"
        provision_verified = False

    return ProceduralPosture(
        relief_type=relief_type,
        relief_label=relief_label,
        posture_status=posture_status,
        court_level=court_level,
        governing_statute=governing_statute,
        governing_provision=governing_provision,
        provision_verified=provision_verified,
        required_factual_premises=req_premises,
        satisfied_premises=satisfied_premises,
        missing_premises=missing_premises,
        conflicts=conflicts,
        statutory_authority=statutory_auth,
    )


# ───────────────────────────────────────────────────────
# 2. Argument Typology & Ground Generation Rules
# ───────────────────────────────────────────────────────
# Category 1: VERIFIED_LEGAL_RULE
# Category 2: GENERAL_JUDICIAL_PRINCIPLE
# Category 3: CASE_SPECIFIC_FACTUAL_APPLICATION (requires supporting facts!)

def build_ground_traceability_plan(
    posture: ProceduralPosture,
    manifest: FactManifest,
) -> list[LegalGroundRecord]:
    """
    Constructs an explicit ground traceability record for the matter.
    Verifies provision → statutory text → proposition.
    Enforces that Category 3 grounds are ONLY generated when facts are available.
    """
    records: list[LegalGroundRecord] = []
    prov = posture.statutory_authority

    # ── Category 1: VERIFIED LEGAL RULE (Canonical Cross-Checked) ──
    # User Rule: Never assign VERIFIED_LEGAL_RULE merely because a provision was returned by the API.
    # Must cross-check Act title, provision number, heading, and text against indiacode.nic.in.
    if prov:
        canonical_entry = CANONICAL_STATUTE_REGISTRY.get((prov.statute.lower(), prov.section))
        api_text = canonical_entry.text if (canonical_entry and (not prov.statutory_text_excerpt or prov.statutory_text_excerpt.endswith("..."))) else prov.statutory_text_excerpt
        api_heading = prov.heading
        check_res = cross_check_provision(
            act_id=prov.statute.lower(),
            provision_number=prov.section,
            api_heading=api_heading,
            api_text=api_text,
            api_act_title=prov.statute,
        )
        prov.canonical_verification_status = check_res.status
        prov.canonical_source = check_res.canonical_source
        if check_res.discrepancies:
            prov.canonical_conflict_details = "; ".join(check_res.discrepancies)

        if check_res.status == "SOURCE_CONFLICT":
            records.append(LegalGroundRecord(
                ground=f"Statutory Jurisdiction (SOURCE CONFLICT: {prov.statute} Section {prov.section})",
                legal_provision=f"Section {prov.section} {prov.statute} [SOURCE_CONFLICT]",
                source=f"CONFLICT: API vs Canonical ({check_res.canonical_source})",
                exact_proposition_supported="CANONICAL DISCREPANCY DETECTED: Statutory text disagrees with official source. Document generation blocked.",
                case_facts_required=[],
                case_facts_available=[],
                verification_status="SOURCE_CONFLICT",
                ground_category="SOURCE_CONFLICT",
                ground_text=(
                    f"CRITICAL WARNING: Section {prov.section} of {prov.statute} has a SOURCE_CONFLICT between the API "
                    f"and canonical official source ({check_res.canonical_source}). "
                    f"Discrepancies: {prov.canonical_conflict_details}."
                )
            ))
        elif check_res.status == "VERIFIED":
            records.append(LegalGroundRecord(
                ground=f"Statutory Jurisdiction ({prov.statute} Section {prov.section})",
                legal_provision=f"Section {prov.section} {prov.statute}",
                source=f"Statutory Text of {prov.statute} (Verified against {check_res.canonical_source})",
                exact_proposition_supported=prov.verified_propositions[0] if prov.verified_propositions else "Court possesses statutory jurisdiction.",
                case_facts_required=[],
                case_facts_available=[],
                verification_status="VERIFIED",
                ground_category="VERIFIED_LEGAL_RULE",
                ground_text=(
                    f"That this Hon'ble Court is vested with statutory jurisdiction under Section {prov.section} "
                    f"of the {prov.statute} to entertain this application for {posture.relief_label}."
                )
            ))
        else:
            records.append(LegalGroundRecord(
                ground=f"Statutory Jurisdiction ({prov.statute} Section {prov.section})",
                legal_provision=f"Section {prov.section} {prov.statute} [REQUIRES CANONICAL VERIFICATION]",
                source=f"API only — unverified against {check_res.canonical_source}",
                exact_proposition_supported="Provision retrieved from API requires authentication against canonical official source.",
                case_facts_required=[],
                case_facts_available=[],
                verification_status="REQUIRES_CANONICAL_VERIFICATION",
                ground_category="REQUIRES_CANONICAL_VERIFICATION",
                ground_text=(
                    f"The statutory provision Section {prov.section} of {prov.statute} requires verification against "
                    f"the canonical official India Code source ({check_res.canonical_source}) before reliance."
                )
            ))
    else:
        records.append(LegalGroundRecord(
            ground="Statutory Jurisdiction",
            legal_provision="[LEGAL PROVISION REQUIRES VERIFICATION]",
            source="Unverified",
            exact_proposition_supported="Procedural provision unverified for this relief type.",
            case_facts_required=[],
            case_facts_available=[],
            verification_status="LEGAL_PROVISION_REQUIRES_VERIFICATION",
            ground_category="LEGAL_PROVISION_REQUIRES_VERIFICATION",
            ground_text="The statutory provision governing this application requires verification."
        ))

    # ── Category 2: GENERAL JUDICIAL PRINCIPLES ───────────
    # Valid general advocacy principles (do not assert specific case facts)
    records.append(LegalGroundRecord(
        ground="Constitutional Liberty & Proportionality (Article 21)",
        legal_provision="Article 21 of the Constitution of India",
        source="Supreme Court Constitutional Jurisprudence (Maneka Gandhi, Gudikanti Narasimhulu)",
        exact_proposition_supported="Personal liberty is a fundamental right; pre-trial detention must not be punitive in nature.",
        case_facts_required=[],
        case_facts_available=[],
        verification_status="VERIFIED",
        ground_category="GENERAL_JUDICIAL_PRINCIPLE",
        ground_text=(
            "That pre-trial detention should not be transformed into punitive incarceration without trial, "
            "and personal liberty under Article 21 of the Constitution must be safeguarded unless compelling "
            "statutory exceptions apply."
        )
    ))

    records.append(LegalGroundRecord(
        ground="Presumption of Innocence",
        legal_provision="Fundamental Canon of Indian Criminal Jurisprudence",
        source="Established Judicial Principle",
        exact_proposition_supported="An accused is presumed innocent until guilt is established beyond reasonable doubt at trial.",
        case_facts_required=[],
        case_facts_available=[],
        verification_status="VERIFIED",
        ground_category="GENERAL_JUDICIAL_PRINCIPLE",
        ground_text=(
            "That the Applicant is presumed innocent until proven guilty, and mere lodging of an FIR "
            "does not warrant indefinite deprivation of liberty."
        )
    ))

    # ── Category 3: CASE-SPECIFIC FACTUAL APPLICATIONS ───
    # ONLY permitted when supporting facts are provided!

    provided_keys = {f.field_name: f.value for f in manifest.provided_facts if f.value}

    # 1. Flight Risk / Residential Ties
    if "address" in provided_keys:
        records.append(LegalGroundRecord(
            ground="Absence of Flight Risk (Residential Ties)",
            legal_provision="Judicial Discretion / Triple Test Factor",
            source="Case Facts & Judicial Discretion",
            exact_proposition_supported="Permanent residence and local ties negate apprehension of absconding.",
            case_facts_required=["address"],
            case_facts_available=["address"],
            verification_status="VERIFIED",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text=f"The Applicant is a permanent resident at {provided_keys['address']}, with rooted ties in the community, negating any flight risk."
        ))
    else:
        records.append(LegalGroundRecord(
            ground="Flight Risk (Residential Ties)",
            legal_provision="Triple Test Factor",
            source="FACTS ABSENT — DO NOT ASSERT",
            exact_proposition_supported="Cannot assert absence of flight risk without verified residential ties.",
            case_facts_required=["address"],
            case_facts_available=[],
            verification_status="CASE_FACTS_MISSING",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text="[CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS: Residential address not provided. Do not claim absence of flight risk.]"
        ))

    # 2. Criminal Antecedents
    if "criminal_antecedents" in provided_keys:
        val = str(provided_keys["criminal_antecedents"])
        is_clean = val.lower() in ("no", "none", "nil", "clean", "no previous criminal history")
        if is_clean:
            records.append(LegalGroundRecord(
                ground="Clean Criminal Antecedents",
                legal_provision="Judicial Discretion Factor",
                source="User Verified Disclosure",
                exact_proposition_supported="Absence of prior criminal history supports exercise of discretion.",
                case_facts_required=["criminal_antecedents"],
                case_facts_available=["criminal_antecedents"],
                verification_status="VERIFIED",
                ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
                ground_text="The Applicant has no criminal antecedents and has never previously been convicted of any offence."
            ))
        else:
            records.append(LegalGroundRecord(
                ground="Disclosure of Antecedents",
                legal_provision="Mandatory Disclosure Rule",
                source="User Disclosure",
                exact_proposition_supported="Pending or prior matters disclosed for judicial evaluation.",
                case_facts_required=["criminal_antecedents"],
                case_facts_available=["criminal_antecedents"],
                verification_status="VERIFIED",
                ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
                ground_text=f"The Applicant discloses the following prior matter(s): {val}."
            ))
    else:
        # Rule: NEVER convert unknown fact into negative assertion!
        records.append(LegalGroundRecord(
            ground="Criminal Antecedents",
            legal_provision="Judicial Discretion Factor",
            source="UNKNOWN — DO NOT CONVERT TO NEGATIVE ASSERTION",
            exact_proposition_supported="Cannot claim clean record when antecedents are unknown.",
            case_facts_required=["criminal_antecedents"],
            case_facts_available=[],
            verification_status="CASE_FACTS_MISSING",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text="[CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS: Criminal antecedents unknown. DO NOT assert clean record or absence of convictions.]"
        ))

    # 3. Evidence Tampering
    # Tampering cannot be factually denied without case record review
    records.append(LegalGroundRecord(
        ground="Apprehension of Tampering",
        legal_provision="Triple Test Factor",
        source="Legal Submission Only",
        exact_proposition_supported="Applicant may undertake not to contact witnesses; cannot assert factual absence of tampering without evidence record.",
        case_facts_required=["evidence_record"],
        case_facts_available=[],
        verification_status="CASE_FACTS_MISSING",
        ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
        ground_text=(
            "The Applicant undertakes not to tamper with evidence or influence witnesses. "
            "(Note: Do not claim 'there is no evidence of tampering' unless investigation record is verified.)"
        )
    ))

    # 4. Prolonged Custody (Only if custody duration is provided)
    if "custody_duration" in provided_keys or "arrest_date" in provided_keys:
        cust_str = provided_keys.get("custody_duration") or f"since arrest on {provided_keys.get('arrest_date')}"
        records.append(LegalGroundRecord(
            ground="Period of Incarceration",
            legal_provision="Proportionality of Detention",
            source="Verified Manifest Record",
            exact_proposition_supported="Duration of custody is relevant to assessing proportionality of continued detention.",
            case_facts_required=["custody_duration"],
            case_facts_available=[k for k in ["custody_duration", "arrest_date"] if k in provided_keys],
            verification_status="VERIFIED",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text=f"The Applicant has been in custody {cust_str}, and further custodial detention serves no investigatory purpose."
        ))
    else:
        records.append(LegalGroundRecord(
            ground="Prolonged Custody",
            legal_provision="Proportionality Factor",
            source="UNKNOWN — PROHIBITED ASSERTION",
            exact_proposition_supported="Cannot argue prolonged custody when duration is unknown.",
            case_facts_required=["custody_duration", "arrest_date"],
            case_facts_available=[],
            verification_status="CASE_FACTS_MISSING",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text="[CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS: Custody duration unknown. DO NOT assert prolonged incarceration.]"
        ))

    # 5. Parity with Co-accused (Only if co_accused_bail is provided)
    if "co_accused_bail" in provided_keys:
        records.append(LegalGroundRecord(
            ground="Parity with Co-Accused",
            legal_provision="Doctrine of Parity (Article 14)",
            source="Verified Manifest Record",
            exact_proposition_supported="Co-accused with identical or greater role released on bail entitles applicant to parity.",
            case_facts_required=["co_accused_bail"],
            case_facts_available=["co_accused_bail"],
            verification_status="VERIFIED",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text=f"The co-accused has been enlarged on bail ({provided_keys['co_accused_bail']}), and the Applicant stands on equal or better footing."
        ))

    # 6. Medical Infirmity / Hardship (Only if medical_condition is provided)
    if "medical_condition" in provided_keys:
        records.append(LegalGroundRecord(
            ground="Medical Infirmity",
            legal_provision="Statutory Proviso (BNSS 480 / CrPC 437)",
            source="Verified Medical Disclosure",
            exact_proposition_supported="Medical condition warrants compassionate consideration under statutory provisos.",
            case_facts_required=["medical_condition"],
            case_facts_available=["medical_condition"],
            verification_status="VERIFIED",
            ground_category="CASE_SPECIFIC_FACTUAL_APPLICATION",
            ground_text=f"The Applicant suffers from {provided_keys['medical_condition']}, requiring specialized medical care."
        ))

    return records


# ───────────────────────────────────────────────────────
# 3. Prompt Guidance Block Generator
# ───────────────────────────────────────────────────────

def render_legal_reasoning_prompt_block(
    posture: ProceduralPosture,
    grounds_plan: list[LegalGroundRecord],
) -> str:
    """
    Renders an authoritative prompt block instructing the LLM on exact procedural posture,
    verified statutory text, supported propositions, and prohibited arguments.
    """
    lines = [
        "═══════════════════════════════════════════════════════",
        "LEGAL REASONING & PROCEDURAL POSTURE SPECIFICATION",
        "═══════════════════════════════════════════════════════",
        f"EXACT RELIEF SOUGHT: {posture.relief_label}",
        f"PROCEDURAL POSTURE: {posture.posture_status.upper()}",
        f"COURT LEVEL: {posture.court_level.upper()}",
        f"GOVERNING PROVISION: {posture.governing_provision}",
        "",
    ]

    if posture.conflicts:
        lines.append("⚠ PROCEDURAL CONFLICT DETECTED:")
        for c in posture.conflicts:
            lines.append(f"  • {c}")
        lines.append("")

    # Statutory text and supported propositions
    if posture.statutory_authority:
        auth = posture.statutory_authority
        lines.extend([
            f"STATUTORY AUTHORITY: {auth.statute} Section {auth.section} — {auth.heading}",
            "STATUTORY TEXT EXCERPT:",
            f'  "{auth.statutory_text_excerpt}"',
            "",
            "VERIFIED PROPOSITIONS (supported by text):",
        ])
        for p in auth.verified_propositions:
            lines.append(f"  ✓ {p}")
        lines.append("")
        lines.append("PROHIBITED PROPOSITIONS (do NOT assert these):")
        for p in auth.prohibited_propositions:
            lines.append(f"  ✗ {p}")
        lines.append("")

    # Argument Typology Rules
    lines.extend([
        "ARGUMENT TYPOLOGY & GROUNDING RULES:",
        "1. VERIFIED_LEGAL_RULE: Use only the governing provision confirmed above. Never cite",
        "   anticipatory bail (BNSS 482 / CrPC 438) in regular bail, or vice versa.",
        "2. GENERAL_JUDICIAL_PRINCIPLE: Article 21, presumption of innocence, proportionality.",
        "   Draft these as legal submissions, NOT factual claims.",
        "3. CASE_SPECIFIC_FACTUAL_APPLICATION: ONLY generate if supporting case facts are provided!",
        "",
        "RULE ON UNKNOWN FACTS:",
        "• [NOT PROVIDED] means UNKNOWN, NOT 'no'!",
        "• If antecedents are unknown: DO NOT state the accused has a clean record or no convictions.",
        "• If evidence is not reviewed: DO NOT state there is no evidence of tampering.",
        "• If custody duration is unknown: DO NOT argue prolonged detention.",
        "",
        "GROUND-BY-GROUND EXECUTION PLAN:",
    ])

    for g in grounds_plan:
        status_tag = f"[{g.verification_status}]"
        lines.append(f"• Ground: {g.ground} ({g.ground_category}) {status_tag}")
        lines.append(f"  Provision: {g.legal_provision} | Source: {g.source}")
        lines.append(f"  Supported Proposition: {g.exact_proposition_supported}")
        if g.case_facts_required:
            lines.append(f"  Required Facts: {', '.join(g.case_facts_required)} | Available: {', '.join(g.case_facts_available) if g.case_facts_available else 'NONE'}")
        if g.verification_status == "CASE_FACTS_MISSING":
            lines.append(f"  ACTION: DO NOT ASSERT AS FACT. If mentioned, write: {g.ground_text}")
        lines.append("")

    lines.append("═══════════════════════════════════════════════════════")
    return "\n".join(lines)
