"""Demo mode router – reset endpoint for guided demo walkthrough."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.models.database import (
    App, AuditLog, ComplianceControl, CostEstimate,
    KnowledgeEntry, MigrationPlan, Wave, get_db,
)

router = APIRouter(prefix="/demo", tags=["Demo Mode"])


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db)):
    """
    Wipe all application data so the guided demo can start fresh.
    Order matters: delete child rows before parent rows.
    """
    db.query(ComplianceControl).delete()
    db.query(CostEstimate).delete()
    db.query(AuditLog).delete()
    db.query(KnowledgeEntry).delete()
    # Unlink apps from waves before deleting waves
    db.query(App).update({"wave_id": None})
    db.query(Wave).delete()
    db.query(MigrationPlan).delete()
    db.query(App).delete()
    db.commit()
    return {"status": "reset", "message": "All demo data cleared."}
