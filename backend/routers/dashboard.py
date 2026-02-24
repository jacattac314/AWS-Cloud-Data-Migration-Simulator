"""Executive Dashboard API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import App, AuditLog, MigrationPlan, Wave, get_db
from backend.models.schemas import AuditLogResponse, DashboardMetrics
from backend.services.compliance_service import get_compliance_score

router = APIRouter(prefix="/dashboard", tags=["Executive Dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(db: Session = Depends(get_db)):
    apps = db.query(App).all()
    total_apps = len(apps)

    apps_migrated = sum(1 for a in apps if a.status in ("Completed", "Migrated"))
    apps_in_progress = sum(1 for a in apps if a.status == "In-Progress")
    apps_pending = total_apps - apps_migrated - apps_in_progress

    migration_pct = round(100 * apps_migrated / total_apps, 1) if total_apps else 0.0

    waves = db.query(Wave).all()
    total_waves = len(waves)
    waves_completed = sum(1 for w in waves if w.status == "Completed")

    total_cost = sum(a.estimated_cost_usd or 0 for a in apps)
    total_savings = sum(
        (a.cost_estimate.estimated_annual_savings if a.cost_estimate else 0) for a in apps
    )

    risk_scores = [a.risk_score or 0 for a in apps]
    avg_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0

    compliance_scores = [get_compliance_score(a) for a in apps]
    avg_compliance = round(sum(compliance_scores) / len(compliance_scores), 1) if compliance_scores else 0.0

    itar_apps = sum(1 for a in apps if a.is_itar)
    pci_apps = sum(1 for a in apps if a.is_pci)
    hipaa_apps = sum(1 for a in apps if a.is_hipaa)

    return DashboardMetrics(
        total_apps=total_apps,
        apps_migrated=apps_migrated,
        apps_in_progress=apps_in_progress,
        apps_pending=apps_pending,
        migration_percent=migration_pct,
        total_waves=total_waves,
        waves_completed=waves_completed,
        total_estimated_cost_usd=round(total_cost, 2),
        total_estimated_savings_usd=round(total_savings, 2),
        avg_risk_score=avg_risk,
        compliance_coverage_percent=avg_compliance,
        itar_apps=itar_apps,
        pci_apps=pci_apps,
        hipaa_apps=hipaa_apps,
    )


@router.get("/waves/breakdown")
def waves_breakdown(db: Session = Depends(get_db)):
    waves = db.query(Wave).order_by(Wave.sequence).all()
    return [
        {
            "wave_name": w.name,
            "sequence": w.sequence,
            "status": w.status,
            "app_count": len(w.apps),
            "risk_score": w.risk_score,
            "start_date": w.start_date,
            "end_date": w.end_date,
        }
        for w in waves
    ]


@router.get("/migration/strategy-distribution")
def strategy_distribution(db: Session = Depends(get_db)):
    """Return count of apps per migration strategy."""
    rows = (
        db.query(App.migration_strategy, func.count(App.id).label("count"))
        .group_by(App.migration_strategy)
        .all()
    )
    return {row.migration_strategy or "Unclassified": row.count for row in rows}


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def get_audit_logs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return logs
