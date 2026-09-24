from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import User, get_db
from services import correction_memory as cm
from utils.auth import get_current_admin_user

router = APIRouter()


def _serialize(row) -> dict:
    return {
        "id": row.id,
        "trigger_type": row.trigger_type,
        "input_signature": row.input_signature,
        "system_output": row.system_output,
        "correct_output": row.correct_output,
        "direction": row.direction,
        "status": row.status,
        "flagged_by": row.flagged_by,
        "flagged_at": row.flagged_at.isoformat() if row.flagged_at else None,
        "note": row.note,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.get("/corrections")
def list_corrections(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """Full correction log, both directions, all statuses, newest first."""
    rows = cm.list_corrections(db)
    return {"corrections": [_serialize(r) for r in rows]}


@router.post("/corrections/{correction_id}/confirm")
def confirm_correction(correction_id: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    row = cm.confirm_correction(db, correction_id, admin.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Correction not found.")
    return _serialize(row)


@router.post("/corrections/{correction_id}/reject")
def reject_correction(correction_id: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    row = cm.reject_correction(db, correction_id, admin.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Correction not found.")
    return _serialize(row)
