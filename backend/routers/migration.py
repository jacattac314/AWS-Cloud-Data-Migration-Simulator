"""Migration Planner API routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from backend.models.database import App, MigrationPlan, Wave, get_db
from backend.models.schemas import (
    AppCreate, AppResponse, AppUpdate, CSVImportResponse,
    PlanCreate, PlanResponse, WaveCreate, WaveResponse,
)
from backend.services.migration_service import (
    classify_and_score_apps, generate_plan, import_apps_from_csv,
)

router = APIRouter(prefix="/migration", tags=["Migration Planner"])


# ─── App CRUD ─────────────────────────────────────────────────────────────────

@router.get("/apps", response_model=List[AppResponse])
def list_apps(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(App).offset(skip).limit(limit).all()


@router.post("/apps", response_model=AppResponse, status_code=201)
def create_app(payload: AppCreate, db: Session = Depends(get_db)):
    app = App(**payload.model_dump())
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.get("/apps/{app_id}", response_model=AppResponse)
def get_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


@router.patch("/apps/{app_id}", response_model=AppResponse)
def update_app(app_id: int, payload: AppUpdate, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(app, field, value)
    db.commit()
    db.refresh(app)
    return app


@router.delete("/apps/{app_id}", status_code=204)
def delete_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    db.delete(app)
    db.commit()


# ─── CSV Import ───────────────────────────────────────────────────────────────

@router.post("/apps/import/csv", response_model=CSVImportResponse, status_code=201)
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
    content = (await file.read()).decode("utf-8", errors="replace")
    imported, skipped, errors = import_apps_from_csv(db, content)
    apps = db.query(App).order_by(App.created_at.desc()).limit(imported).all()
    return CSVImportResponse(imported=imported, skipped=skipped, errors=errors, apps=apps)


# ─── Classification ───────────────────────────────────────────────────────────

@router.post("/apps/classify", response_model=List[AppResponse])
def classify_apps(
    app_ids: Optional[List[int]] = None,
    db: Session = Depends(get_db),
):
    """Run auto-classification and cost/risk scoring on all (or selected) apps."""
    apps = classify_and_score_apps(db, app_ids)
    return apps


# ─── Plans ────────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=List[PlanResponse])
def list_plans(db: Session = Depends(get_db)):
    return db.query(MigrationPlan).order_by(MigrationPlan.created_at.desc()).all()


@router.post("/plans/generate", response_model=PlanResponse, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    try:
        plan = generate_plan(db, payload.name, payload.description or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return plan


@router.get("/plans/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(MigrationPlan).filter(MigrationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(MigrationPlan).filter(MigrationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    db.delete(plan)
    db.commit()


# ─── Waves ────────────────────────────────────────────────────────────────────

@router.get("/waves", response_model=List[WaveResponse])
def list_waves(plan_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Wave)
    if plan_id:
        q = q.filter(Wave.plan_id == plan_id)
    return q.order_by(Wave.sequence).all()


@router.patch("/waves/{wave_id}", response_model=WaveResponse)
def update_wave(wave_id: int, status: str, db: Session = Depends(get_db)):
    wave = db.query(Wave).filter(Wave.id == wave_id).first()
    if not wave:
        raise HTTPException(status_code=404, detail="Wave not found")
    wave.status = status
    db.commit()
    db.refresh(wave)
    return wave
