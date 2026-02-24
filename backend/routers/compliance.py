"""Compliance Module API routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models.database import App, get_db
from backend.models.schemas import (
    AppResponse, ComplianceControlResponse, ComplianceReportResponse,
    ComplianceUpdateRequest,
)
from backend.services.compliance_service import (
    generate_compliance_report, mark_control, sync_controls_for_app, update_compliance_flag,
    get_compliance_score,
)

router = APIRouter(prefix="/compliance", tags=["Compliance"])


@router.get("/apps/{app_id}/controls", response_model=List[ComplianceControlResponse])
def get_app_controls(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    sync_controls_for_app(db, app)
    return app.compliance_controls


@router.patch("/apps/{app_id}/tags", response_model=AppResponse)
def update_compliance_tags(
    app_id: int,
    is_itar: bool = None,
    is_pci: bool = None,
    is_hipaa: bool = None,
    db: Session = Depends(get_db),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    update_compliance_flag(db, app, is_itar=is_itar, is_pci=is_pci, is_hipaa=is_hipaa)
    db.refresh(app)
    return app


@router.patch("/controls/{control_id}", response_model=ComplianceControlResponse)
def update_control(payload: ComplianceUpdateRequest, db: Session = Depends(get_db)):
    ctrl = mark_control(db, payload.control_id, payload.is_implemented, payload.notes)
    if not ctrl:
        raise HTTPException(status_code=404, detail="Control not found")
    return ctrl


@router.get("/apps/{app_id}/report", response_model=ComplianceReportResponse)
def get_compliance_report(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    sync_controls_for_app(db, app)
    report_data = generate_compliance_report(db, app)
    return ComplianceReportResponse(
        app_id=report_data["app_id"],
        app_name=report_data["app_name"],
        frameworks=report_data["frameworks"],
        controls=app.compliance_controls,
        compliance_score=report_data["compliance_score"],
        generated_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/summary")
def compliance_summary(db: Session = Depends(get_db)):
    """Return a high-level compliance summary across all apps."""
    apps = db.query(App).all()
    total = len(apps)
    itar_count = sum(1 for a in apps if a.is_itar)
    pci_count = sum(1 for a in apps if a.is_pci)
    hipaa_count = sum(1 for a in apps if a.is_hipaa)
    scores = [get_compliance_score(a) for a in apps]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    fully_compliant = sum(1 for s in scores if s == 100.0)
    return {
        "total_apps": total,
        "itar_apps": itar_count,
        "pci_apps": pci_count,
        "hipaa_apps": hipaa_count,
        "avg_compliance_score": avg_score,
        "fully_compliant_apps": fully_compliant,
        "non_compliant_apps": total - fully_compliant,
    }
