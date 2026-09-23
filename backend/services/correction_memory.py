from datetime import datetime
from sqlalchemy.orm import Session

from models.database import Correction

# Fixed ordering used to infer direction automatically -- never trust a client
# to self-report which direction its own correction moves the verdict.
STATE_ORDER = {
    "Not found in indexed corpus": 0,
    "Mismatch": 1,
    "Verified": 2,
}


def normalize_signature(case_name: str, citation_string: str) -> str:
    # Reuses the exact same name-normalization already used for case resolution
    # (services.citation_verifier._normalize_name), so a correction recorded
    # against a citation matches that same citation's raw extracted text the
    # next time it's seen -- not a separate, potentially-inconsistent scheme.
    from services.citation_verifier import _normalize_name
    return f"{_normalize_name(case_name)}|{(citation_string or '').strip().lower()}"


def compute_direction(system_output: str, correct_output: str) -> str:
    if system_output not in STATE_ORDER or correct_output not in STATE_ORDER:
        raise ValueError(f"Unknown verdict state: system_output={system_output!r}, correct_output={correct_output!r}")
    return "loosen" if STATE_ORDER[correct_output] > STATE_ORDER[system_output] else "tighten"


def create_correction(
    db: Session, *, trigger_type: str, case_name: str, citation_string: str,
    system_output: str, correct_output: str, flagged_by: str, note: str = None,
) -> Correction:
    if correct_output not in STATE_ORDER:
        raise ValueError(f"correct_output must be one of {list(STATE_ORDER)}")
    if correct_output == system_output:
        raise ValueError("correct_output must differ from system_output")

    direction = compute_direction(system_output, correct_output)
    # THE rule: tighten (toward Mismatch/Not-found) takes effect immediately,
    # on a single flag -- it can only ever make the system more cautious.
    # loosen (toward Verified) starts pending_review and has zero effect
    # until an admin explicitly confirms it -- a single unconfirmed flag must
    # never be able to make the system more confident on its own.
    status = "confirmed" if direction == "tighten" else "pending_review"

    row = Correction(
        trigger_type=trigger_type,
        input_signature=normalize_signature(case_name, citation_string),
        system_output=system_output,
        correct_output=correct_output,
        direction=direction,
        status=status,
        flagged_by=flagged_by,
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def check_correction(db: Session, case_name: str, citation_string: str) -> Correction | None:
    """THE lookup the verification pipeline calls before resolve_case(). Only ever
    returns status='confirmed' rows -- a pending_review (loosen) correction is
    invisible here by construction, not by convention, so there's no code path
    that could accidentally let an unconfirmed flag affect a live result."""
    signature = normalize_signature(case_name, citation_string)
    return (
        db.query(Correction)
        .filter(Correction.input_signature == signature, Correction.status == "confirmed")
        .order_by(Correction.flagged_at.desc())
        .first()
    )


def confirm_correction(db: Session, correction_id: str, admin_user_id: str) -> Correction | None:
    row = db.query(Correction).filter(Correction.id == correction_id).first()
    if not row:
        return None
    if row.status != "pending_review":
        return row  # idempotent: confirming an already-decided row is a no-op
    row.status = "confirmed"
    row.reviewed_by = admin_user_id
    row.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def reject_correction(db: Session, correction_id: str, admin_user_id: str) -> Correction | None:
    row = db.query(Correction).filter(Correction.id == correction_id).first()
    if not row:
        return None
    if row.status != "pending_review":
        return row  # idempotent
    row.status = "rejected"
    row.reviewed_by = admin_user_id
    row.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_corrections(db: Session) -> list:
    return db.query(Correction).order_by(Correction.flagged_at.desc()).all()
