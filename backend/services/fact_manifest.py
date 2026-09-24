"""
Fact Manifest Service
=====================
Parses user input into a structured manifest that explicitly categorizes
every piece of information as provided / not_provided / requires_verification.

The manifest is passed to the LLM so it can never confuse "user said this"
with "I should probably assume this."
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import re
import json


# ───────────────────────────────────────────────────────
# Core data structures
# ───────────────────────────────────────────────────────

@dataclass
class FactEntry:
    field_name: str                      # e.g. "arrest_date"
    label: str                           # e.g. "Date of Arrest"
    value: Optional[str] = None          # actual value or None
    source: str = "not_provided"         # "user_input" | "source_document" | "not_provided"
    material: bool = False               # is this material to the legal application?
    category: str = "factual"            # "factual" | "procedural" | "legal" | "personal"


@dataclass
class FactManifest:
    document_type: str
    provided_facts: list[FactEntry] = field(default_factory=list)
    missing_facts: list[FactEntry] = field(default_factory=list)
    all_fields: list[FactEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_block(self) -> str:
        """Render the manifest as a structured text block enforcing statement classification."""
        lines = [
            "=" * 60,
            "FACT MANIFEST & SOURCE TRACEABILITY (RULES 1, 2, 3, 10)",
            "=" * 60,
            f"Document Type: {self.document_type}",
            "",
            "── USER_FACT / DOCUMENT_FACT (Verified — state ONLY these as case facts) ──",
        ]
        if self.provided_facts:
            for f in self.provided_facts:
                src_tag = "USER_FACT" if f.source in ("user_input", "structured_input") else "DOCUMENT_FACT"
                lines.append(f"  • {f.label}: {f.value}  [CLASSIFICATION: {src_tag}]")
        else:
            lines.append("  (No facts were provided by the user or source documents.)")

        lines.append("")
        lines.append("── UNKNOWN / REQUIRES_VERIFICATION (MUST use [NOT PROVIDED] or [REQUIRES VERIFICATION]) ──")
        if self.missing_facts:
            for f in self.missing_facts:
                mat = " ⚠ MATERIAL" if f.material else ""
                lines.append(f"  • {f.label}: [NOT PROVIDED]{mat}  [CLASSIFICATION: UNKNOWN]")
        else:
            lines.append("  (All fields were provided.)")

        lines.append("")
        lines.append("GROUNDING ENFORCEMENT:")
        lines.append("• Only USER_FACT and DOCUMENT_FACT may be stated as facts about the case.")
        lines.append("• UNKNOWN / REQUIRES_VERIFICATION must NEVER be converted into factual assertions.")
        lines.append("• Never confuse absence of data with absence of a fact (e.g. no antecedent info ≠ 'no antecedents').")
        lines.append("• For any missing case-specific ground, use [CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS].")
        lines.append("=" * 60)
        return "\n".join(lines)


# ───────────────────────────────────────────────────────
# Field schemas per document type
# ───────────────────────────────────────────────────────
# Each entry: (field_name, label, material?, category)

_BAIL_FIELDS = [
    ("accused_name",       "Name of Accused/Applicant",    True,  "personal"),
    ("father_name",        "Father's Name",                False, "personal"),
    ("age",                "Age",                          False, "personal"),
    ("address",            "Residential Address",          False, "personal"),
    ("fir_number",         "FIR Number",                   True,  "factual"),
    ("fir_date",           "FIR Date",                     True,  "factual"),
    ("police_station",     "Police Station",               True,  "factual"),
    ("district",           "District",                     True,  "factual"),
    ("sections",           "Sections/Offences Invoked",    True,  "legal"),
    ("statute",            "Applicable Statute (BNS/IPC/Special Act)", False, "legal"),
    ("court",              "Court / Jurisdiction",          True,  "procedural"),
    ("arrest_date",        "Date of Arrest",               True,  "factual"),
    ("custody_status",     "Custody Status (Judicial/Police/Not Arrested)", True, "factual"),
    ("custody_duration",   "Duration in Custody",          False, "factual"),
    ("investigation_status", "Investigation Status (Ongoing/Complete)", False, "procedural"),
    ("chargesheet_status", "Chargesheet Filed (Yes/No)",   False, "procedural"),
    ("charges_framed",     "Charges Framed (Yes/No)",      False, "procedural"),
    ("trial_status",       "Trial Status (Not Started/Ongoing/Completed)", False, "procedural"),
    ("criminal_antecedents", "Criminal Antecedents (Yes/No/Details)", False, "factual"),
    ("previous_bail_apps", "Previous Bail Applications & Outcomes", False, "procedural"),
    ("pending_firs",       "Other Pending FIRs (Yes/No/Details)", False, "factual"),
    ("nbw_status",         "Non-Bailable Warrants (Yes/No)", False, "procedural"),
    ("co_accused_bail",    "Co-accused Bail Status",       False, "procedural"),
    ("brief_facts",        "Brief Facts / Defence",        True,  "factual"),
    ("employment",         "Employment / Occupation",      False, "personal"),
    ("family_ties",        "Family Ties / Dependents",     False, "personal"),
    ("medical_condition",  "Medical Condition (if any)",   False, "personal"),
    ("surety_details",     "Surety Details",               False, "personal"),
    ("case_date",          "Date of Incident/Offence",     False, "factual"),
]

_ANTICIPATORY_BAIL_FIELDS = [
    ("applicant_name",     "Name of Applicant",            True,  "personal"),
    ("father_name",        "Father's Name",                False, "personal"),
    ("age",                "Age",                          False, "personal"),
    ("address",            "Residential Address",          False, "personal"),
    ("police_station",     "Police Station",               True,  "factual"),
    ("district",           "District",                     True,  "factual"),
    ("fir_number",         "FIR Number (if registered)",   False, "factual"),
    ("fir_date",           "FIR Date",                     False, "factual"),
    ("sections",           "Apprehended Offence / Sections", True, "legal"),
    ("statute",            "Applicable Statute",           False, "legal"),
    ("court",              "Court / Jurisdiction",          True,  "procedural"),
    ("apprehension_reason", "Reason for Apprehension of Arrest", True, "factual"),
    ("brief_facts",        "Brief Facts / Reasons",        True,  "factual"),
    ("criminal_antecedents", "Criminal Antecedents",       False, "factual"),
    ("employment",         "Employment / Occupation",      False, "personal"),
    ("case_date",          "Date of Incident/Offence",     False, "factual"),
]

_CIVIL_SUIT_FIELDS = [
    ("plaintiff",          "Plaintiff Name & Address",     True,  "personal"),
    ("defendant",          "Defendant Name & Address",     True,  "personal"),
    ("court",              "Court / Jurisdiction",          True,  "procedural"),
    ("suit_value",         "Suit Valuation",               True,  "factual"),
    ("cause_of_action",    "Cause of Action",              True,  "factual"),
    ("cause_date",         "Date Cause of Action Arose",   False, "factual"),
    ("relief_sought",      "Relief Sought",                True,  "factual"),
    ("limitation_period",  "Limitation Period Compliance", False, "procedural"),
    ("previous_proceedings", "Previous Proceedings (if any)", False, "procedural"),
    ("property_details",   "Property / Subject Matter Details", False, "factual"),
    ("brief_facts",        "Brief Facts",                  True,  "factual"),
]

_RENT_AGREEMENT_FIELDS = [
    ("landlord",           "Landlord Name & Address",      True,  "personal"),
    ("tenant",             "Tenant Name & Address",        True,  "personal"),
    ("property_address",   "Property Address",             True,  "factual"),
    ("monthly_rent",       "Monthly Rent Amount",          True,  "factual"),
    ("security_deposit",   "Security Deposit",             False, "factual"),
    ("duration",           "Agreement Duration",           True,  "factual"),
    ("start_date",         "Commencement Date",            False, "factual"),
    ("purpose",            "Purpose of Tenancy",           False, "factual"),
    ("maintenance_terms",  "Maintenance Responsibility",   False, "factual"),
    ("notice_period",      "Notice Period for Termination", False, "factual"),
]

_EMPLOYMENT_FIELDS = [
    ("company",            "Company / Employer Name",      True,  "personal"),
    ("employee",           "Employee Name",                True,  "personal"),
    ("job_title",          "Job Title / Designation",      True,  "factual"),
    ("salary",             "Annual CTC / Salary",          True,  "factual"),
    ("start_date",         "Joining / Commencement Date",  False, "factual"),
    ("probation_period",   "Probation Period",             False, "factual"),
    ("notice_period",      "Notice Period",                False, "factual"),
    ("work_location",      "Work Location",                False, "factual"),
    ("reporting_to",       "Reporting Authority",          False, "factual"),
]

_NDA_FIELDS = [
    ("disclosing_party",   "Disclosing Party",             True,  "personal"),
    ("receiving_party",    "Receiving Party",              True,  "personal"),
    ("purpose",            "Purpose of Disclosure",        True,  "factual"),
    ("duration",           "Duration of Obligation",       True,  "factual"),
    ("governing_law",      "Governing Law / Jurisdiction", False, "legal"),
    ("effective_date",     "Effective Date",               False, "factual"),
]

_VAKALATNAMA_FIELDS = [
    ("court",              "Court Name",                   True,  "procedural"),
    ("client_name",        "Client Name",                  True,  "personal"),
    ("advocate_name",      "Advocate Name",                True,  "personal"),
    ("case_number",        "Case Number",                  True,  "procedural"),
    ("client_address",     "Client Address",               False, "personal"),
    ("advocate_enrollment", "Advocate Enrollment Number",  False, "personal"),
]

_AFFIDAVIT_FIELDS = [
    ("deponent_name",      "Deponent Name",                True,  "personal"),
    ("father_name",        "Father's Name",                False, "personal"),
    ("age",                "Age",                          False, "personal"),
    ("address",            "Address",                      False, "personal"),
    ("related_matter",     "Related Matter / Purpose",     True,  "factual"),
    ("court",              "Court (if applicable)",        False, "procedural"),
    ("case_number",        "Case Number (if applicable)",  False, "procedural"),
]

_INJUNCTION_FIELDS = [
    ("applicant",          "Applicant Name",               True,  "personal"),
    ("respondent",         "Respondent Name",              True,  "personal"),
    ("court",              "Court / Jurisdiction",          True,  "procedural"),
    ("subject_matter",     "Subject Matter / Property",    True,  "factual"),
    ("urgency_grounds",    "Grounds of Urgency",           True,  "factual"),
    ("relief_sought",      "Relief Sought",                False, "factual"),
    ("previous_proceedings", "Previous Proceedings",       False, "procedural"),
]

# Fallback for any document type not explicitly listed
_GENERIC_FIELDS = [
    ("party_1",            "First Party",                  True,  "personal"),
    ("party_2",            "Second Party / Opposite Party", False, "personal"),
    ("court",              "Court / Jurisdiction",          False, "procedural"),
    ("subject",            "Subject / Purpose",            True,  "factual"),
    ("brief_facts",        "Brief Facts / Description",    True,  "factual"),
    ("date",               "Relevant Date",                False, "factual"),
]


# ───────────────────────────────────────────────────────
# Template ID → field schema mapping
# ───────────────────────────────────────────────────────

TEMPLATE_FIELD_SCHEMAS: dict[str, list[tuple]] = {
    "bail":           _BAIL_FIELDS,
    "anticipatory":   _ANTICIPATORY_BAIL_FIELDS,
    "plaint":         _CIVIL_SUIT_FIELDS,
    "injunction":     _INJUNCTION_FIELDS,
    "rent":           _RENT_AGREEMENT_FIELDS,
    "employment":     _EMPLOYMENT_FIELDS,
    "nda":            _NDA_FIELDS,
    "vakalatnama":    _VAKALATNAMA_FIELDS,
    "affidavit":      _AFFIDAVIT_FIELDS,
}

# Frontend field ID → manifest field name mapping per template
# (Maps the short field IDs used in DraftAssistant.jsx to the canonical field names above)
FRONTEND_FIELD_MAP: dict[str, dict[str, str]] = {
    "bail": {
        "accused":  "accused_name",
        "fir":      "fir_number",
        "sections": "sections",
        "court":    "court",
        "facts":    "brief_facts",
    },
    "anticipatory": {
        "apprehended": "applicant_name",
        "ps":          "police_station",
        "offense":     "sections",
        "court":       "court",
        "reasons":     "brief_facts",
    },
    "plaint": {
        "plaintiff":  "plaintiff",
        "defendant":  "defendant",
        "court":      "court",
        "suitValue":  "suit_value",
        "cause":      "cause_of_action",
    },
    "injunction": {
        "applicant":  "applicant",
        "respondent": "respondent",
        "court":      "court",
        "property":   "subject_matter",
        "urgency":    "urgency_grounds",
    },
    "rent": {
        "landlord":  "landlord",
        "tenant":    "tenant",
        "property":  "property_address",
        "rent":      "monthly_rent",
        "duration":  "duration",
    },
    "employment": {
        "company":   "company",
        "employee":  "employee",
        "role":      "job_title",
        "salary":    "salary",
        "probation": "probation_period",
    },
    "nda": {
        "party1":    "disclosing_party",
        "party2":    "receiving_party",
        "purpose":   "purpose",
        "duration":  "duration",
    },
    "vakalatnama": {
        "court":    "court",
        "client":   "client_name",
        "advocate": "advocate_name",
        "caseNo":   "case_number",
    },
    "affidavit": {
        "deponent": "deponent_name",
        "age":      "age",
        "address":  "address",
        "matter":   "related_matter",
    },
}


# ───────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────

def _guess_template_id(description: str, category: str | None) -> str:
    """Best-effort guess of template ID from the description/category text."""
    text = (description + " " + (category or "")).lower()
    if "anticipatory" in text:
        return "anticipatory"
    if "bail" in text:
        return "bail"
    if "plaint" in text or "civil suit" in text:
        return "plaint"
    if "injunction" in text:
        return "injunction"
    if "rent" in text or "lease" in text:
        return "rent"
    if "employment" in text or "appointment" in text:
        return "employment"
    if "nda" in text or "non-disclosure" in text or "confidentiality" in text:
        return "nda"
    if "vakalatnama" in text:
        return "vakalatnama"
    if "affidavit" in text:
        return "affidavit"
    return "__generic__"


def _parse_description_fields(description: str) -> dict[str, str]:
    """Extract key-value pairs from the prose description built by the frontend.

    The frontend's buildDescription() produces lines like:
      "Name of Accused: Ramesh Kumar"
      "FIR No. / Year: 124/2023"
    """
    fields = {}
    lines = description.strip().split("\n")
    for line in lines:
        # Skip the header line "Generate a ... with the following details:"
        if line.strip().startswith("Generate a ") and "details:" in line:
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                fields[key] = val
    return fields


def _match_parsed_to_schema(
    parsed: dict[str, str],
    template_id: str,
    schema: list[tuple],
) -> dict[str, str]:
    """Match parsed description fields to canonical schema field names.

    Uses the FRONTEND_FIELD_MAP first (exact match on frontend field IDs),
    then falls back to fuzzy label matching.
    """
    matched: dict[str, str] = {}
    fe_map = FRONTEND_FIELD_MAP.get(template_id, {})

    # Build a reverse lookup: label (lowercase) → field_name
    label_to_field = {}
    for field_name, label, _mat, _cat in schema:
        label_to_field[label.lower()] = field_name

    for key, val in parsed.items():
        key_lower = key.lower().strip()

        # 1. Direct frontend field-ID match
        if key_lower in fe_map:
            matched[fe_map[key_lower]] = val
            continue

        # 2. Exact label match
        if key_lower in label_to_field:
            matched[label_to_field[key_lower]] = val
            continue

        # 3. Substring match on labels
        for label_lower, field_name in label_to_field.items():
            if key_lower in label_lower or label_lower in key_lower:
                if field_name not in matched:
                    matched[field_name] = val
                    break

    return matched


def build_manifest(
    description: str,
    category: str | None = None,
    template_id: str | None = None,
    structured_input: dict | None = None,
) -> FactManifest:
    """Build a FactManifest from user input.

    Parameters
    ----------
    description : str
        The prose description from buildDescription() or a free-text description.
    category : str | None
        Document category hint (e.g. "Petition", "Agreement").
    template_id : str | None
        Explicit template ID from frontend (e.g. "bail", "rent").
    structured_input : dict | None
        Optional structured input with provided_fields and empty_fields.
    """
    tid = template_id or _guess_template_id(description, category)
    schema = TEMPLATE_FIELD_SCHEMAS.get(tid, _GENERIC_FIELDS)

    # Determine document type display name
    doc_type_names = {
        "bail": "Bail Application",
        "anticipatory": "Anticipatory Bail Application",
        "plaint": "Civil Suit / Plaint",
        "injunction": "Injunction Application",
        "rent": "Rent Agreement",
        "employment": "Employment Contract",
        "nda": "Non-Disclosure Agreement",
        "vakalatnama": "Vakalatnama",
        "affidavit": "Affidavit",
        "__generic__": "Legal Document",
    }
    doc_type = doc_type_names.get(tid, "Legal Document")

    # Collect provided values from structured_input or parsed description
    provided_values: dict[str, str] = {}

    if structured_input and isinstance(structured_input, dict):
        pf = structured_input.get("provided_fields", {})
        fe_map = FRONTEND_FIELD_MAP.get(tid, {})
        for fe_key, val in pf.items():
            canon = fe_map.get(fe_key, fe_key)
            if val and str(val).strip():
                provided_values[canon] = str(val).strip()
    else:
        # Parse from prose description
        parsed = _parse_description_fields(description)
        provided_values = _match_parsed_to_schema(parsed, tid, schema)

    # Build fact entries
    all_fields = []
    provided_facts = []
    missing_facts = []

    for field_name, label, material, cat in schema:
        val = provided_values.get(field_name)
        if val:
            entry = FactEntry(
                field_name=field_name,
                label=label,
                value=val,
                source="user_input",
                material=material,
                category=cat,
            )
            provided_facts.append(entry)
        else:
            entry = FactEntry(
                field_name=field_name,
                label=label,
                value=None,
                source="not_provided",
                material=material,
                category=cat,
            )
            missing_facts.append(entry)
        all_fields.append(entry)

    return FactManifest(
        document_type=doc_type,
        provided_facts=provided_facts,
        missing_facts=missing_facts,
        all_fields=all_fields,
    )
