import pytest
from services.review_engine import run_hybrid_review, auto_fix_draft
from services.statute_map import validate_sections_in_text
from services.legal_reasoning_engine import identify_procedural_posture
from services.fact_manifest import build_manifest


def test_review_engine_detects_legacy_statutes_without_bnss():
    """Verify that Draft Review detects missing 2023 Sanhitas alignment when legacy CrPC/IPC is cited alone."""
    legacy_draft = """
    IN THE COURT OF SESSIONS JUDGE AT NEW DELHI
    BAIL APPLICATION NO. 101 OF 2024
    IN THE MATTER OF:
    Ramesh Kumar ... Applicant
    VERSUS
    State of NCT of Delhi ... Respondent

    APPLICATION UNDER SECTION 439 OF THE CODE OF CRIMINAL PROCEDURE, 1973 FOR REGULAR BAIL
    IN FIR NO. 45/2024 UNDER SECTION 420 OF INDIAN PENAL CODE, 1860 AT P.S. HAUZ KHAS.

    MOST RESPECTFULLY SHOWETH:
    1. That the applicant was arrested on 10.08.2024 and is in judicial custody.
    2. That the applicant has clean antecedents and no criminal history.
    3. That there is no possibility of witness tampering.

    PRAYER:
    It is prayed that regular bail be granted.
    """
    review = run_hybrid_review(legacy_draft, "Bail Application")

    # Should detect current-law alignment need
    crit_ids = [c.id for c in review.critical]
    assert "CURRENT_LAW_ALIGNMENT_REQUIRED" in crit_ids, f"Expected CURRENT_LAW_ALIGNMENT_REQUIRED in {crit_ids}"

    # Should detect missing Annexure index
    warn_ids = [w.id for w in review.warnings]
    assert "MISSING_ANNEXURE_INDEX" in warn_ids, f"Expected MISSING_ANNEXURE_INDEX in {warn_ids}"

    # Should detect missing synopsis / affidavit
    assert any("Synopsis" in sec for sec in review.missing_sections)
    assert any("Annexures" in sec for sec in review.missing_sections)


def test_statute_validation_maps_crpc_and_ipc_to_bnss_and_bns():
    """Verify statute_map correctly extracts and maps legacy sections."""
    text = "Application under Section 439 CrPC in FIR under Section 420 IPC"
    refs = validate_sections_in_text(text)
    ref_map = {r.section: r for r in refs}

    assert "439" in ref_map
    assert "483" in ref_map["439"].note or ref_map["439"].statute == "CrPC"

    assert "420" in ref_map
    assert "318" in ref_map["420"].note or ref_map["420"].statute == "IPC"


def test_procedural_posture_extraction():
    """Verify procedural posture correctly identifies regular bail vs anticipatory bail."""
    text = "Application under Section 483 BNSS for regular bail. Accused is in judicial custody."
    posture = identify_procedural_posture(text)
    assert posture.relief_type == "regular_bail"

    ab_text = "Application under Section 482 BNSS for anticipatory bail. Applicant apprehends arrest."
    ab_posture = identify_procedural_posture(ab_text)
    assert ab_posture.relief_type == "anticipatory_bail"


def test_auto_fix_draft_system_prompt_includes_sanhitas_and_annexures(monkeypatch):
    """Verify auto_fix_draft prepares prompt with BNSS/BNS mappings and annexure instructions."""
    captured = {}

    def mock_call_llm(sys_prompt, user_msg, json_mode=False, **kwargs):
        captured["sys_prompt"] = sys_prompt
        captured["user_msg"] = user_msg
        return """
SECTION I: SYNOPSIS & LIST OF DATES AND EVENTS
10.08.2024: Accused arrested

SECTION II: CAUSE TITLE
IN THE COURT OF SESSIONS JUDGE
APPLICATION UNDER SECTION 483 BNSS (SECTION 439 CrPC)

SECTION III: APPLICATION
1. FIR copy marked as ANNEXURE A-1.

SECTION IV: GROUNDS
Ground A: Dual statute compliance.

SECTION V: PRAYER
Grant bail.

SECTION VI: INDEX OF ANNEXURES
| S.No. | Annexure Mark | Particulars | Page No. |
| 1. | Annexure A-1 | True copy of FIR | 1 |

SECTION VII: AFFIDAVIT IN SUPPORT
Deponent solemnly affirms that Annexure A-1 is a true copy.

SECTION VIII: VERIFICATION
Verified at Delhi.
"""

    monkeypatch.setattr("services.review_engine.call_llm", mock_call_llm)

    legacy_draft = "Application under Section 439 CrPC in FIR 45/2024 under Section 420 IPC"
    res = auto_fix_draft(
        draft=legacy_draft,
        issues=[{"id": "CURRENT_LAW_ALIGNMENT_REQUIRED", "title": "Missing BNSS"}],
        missing_sections=["Index of Annexures", "Synopsis & List of Dates"],
        missing_fields=[],
    )

    sys_prompt = captured.get("sys_prompt", "")
    assert "CURRENT-LAW ALIGNMENT & DUAL-STATUTE HARMONIZATION" in sys_prompt
    assert "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)" in sys_prompt
    assert "Section 483" in sys_prompt
    assert "COURT-STYLE PRESENTATION & ANNEXURE/DOCUMENT HANDLING" in sys_prompt
    assert "SECTION VI: FORMAL INDEX OF ANNEXURES TABLE" in sys_prompt
    assert "SECTION VII: AFFIDAVIT IN SUPPORT OF APPLICATION" in sys_prompt

    assert any("2023 Sanhitas" in c for c in res.changes_made)
    assert any("Index of Annexures" in c for c in res.changes_made)


def test_documents_draft_system_prompt_has_full_court_pleading_sections():
    """Verify documents.py DRAFT_SYSTEM_PROMPT includes the complete 8-part court pleading design."""
    from routes.documents import DRAFT_SYSTEM_PROMPT

    assert "SECTION I: SYNOPSIS & LIST OF DATES AND EVENTS" in DRAFT_SYSTEM_PROMPT
    assert "SECTION II: COMPLETE CAUSE TITLE & MEMO OF PARTIES" in DRAFT_SYSTEM_PROMPT
    assert "SECTION III: APPLICATION / FACTUAL MATRIX WITH IN-TEXT ANNEXURE CITATIONS" in DRAFT_SYSTEM_PROMPT
    assert "SECTION VI: FORMAL INDEX OF ANNEXURES / EXHIBITS TABLE" in DRAFT_SYSTEM_PROMPT
    assert "SECTION VII: AFFIDAVIT IN SUPPORT OF APPLICATION" in DRAFT_SYSTEM_PROMPT
    assert "SECTION VIII: FORMAL VERIFICATION & COUNSEL ATTESTATION" in DRAFT_SYSTEM_PROMPT

