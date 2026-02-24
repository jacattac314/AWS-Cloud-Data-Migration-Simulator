"""Migration planning service – classification, wave grouping, risk & cost estimation."""

from __future__ import annotations

import io
import random
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from backend.models.database import App, AuditLog, CostEstimate, MigrationPlan, Wave


# ─── Strategy Classification ─────────────────────────────────────────────────

# Keywords that suggest a particular migration strategy
REHOST_SIGNALS = {
    "java", "tomcat", "jboss", "iis", "linux", "windows", "oracle", "mssql",
    "mysql", "postgresql", "nginx", "apache", "php", "perl", "ruby",
}
REPLATFORM_SIGNALS = {
    "spring", "django", ".net core", "node", "nodejs", "express",
    "flask", "rails", "docker", "container",
}
REFACTOR_SIGNALS = {
    "monolith", "legacy", "cobol", "mainframe", "as400", "vb6",
    "silverlight", "jquery", "struts",
}

SENSITIVITY_WEIGHT = {"Low": 0.2, "Medium": 0.5, "High": 0.8, "Critical": 1.0}
SLA_WEIGHT = {"Basic": 0.1, "Standard": 0.3, "Premium": 0.6, "Mission-Critical": 1.0}


def classify_strategy(tech_stack: Optional[str], data_volume_gb: float) -> str:
    """Classify an app into Rehost / Replatform / Refactor based on tech signals."""
    if not tech_stack:
        return "Rehost"
    ts = tech_stack.lower()

    refactor_hits = sum(1 for k in REFACTOR_SIGNALS if k in ts)
    replatform_hits = sum(1 for k in REPLATFORM_SIGNALS if k in ts)
    rehost_hits = sum(1 for k in REHOST_SIGNALS if k in ts)

    # Large data volumes lean toward rehost (least risky)
    if data_volume_gb > 500:
        rehost_hits += 2

    if refactor_hits >= replatform_hits and refactor_hits >= rehost_hits and refactor_hits > 0:
        return "Refactor"
    if replatform_hits > rehost_hits and replatform_hits > 0:
        return "Replatform"
    return "Rehost"


def compute_risk_score(app: App) -> float:
    """Return a risk score [0..10] for an app based on sensitivity, SLA, compliance flags."""
    score = 0.0
    score += SENSITIVITY_WEIGHT.get(app.data_sensitivity or "Low", 0.2) * 4
    score += SLA_WEIGHT.get(app.sla_tier or "Standard", 0.3) * 3
    if app.is_itar:
        score += 1.5
    if app.is_pci:
        score += 1.0
    if app.is_hipaa:
        score += 0.8
    strategy_penalty = {"Refactor": 1.0, "Replatform": 0.5, "Rehost": 0.0}
    score += strategy_penalty.get(app.migration_strategy or "Rehost", 0.0)
    return round(min(score, 10.0), 2)


def estimate_cost(app: App) -> Tuple[float, float, float, float]:
    """
    Returns (monthly_aws_cost, monthly_on_prem_cost, migration_one_time_cost, annual_savings).
    Uses a simple rule-based model.
    """
    volume = app.data_volume_gb or 0.0
    base_aws = 150 + volume * 0.023            # S3-like storage
    base_on_prem = 400 + volume * 0.05         # on-prem estimate

    if app.migration_strategy == "Replatform":
        base_aws *= 1.2
    elif app.migration_strategy == "Refactor":
        base_aws *= 0.8                        # refactored apps are usually leaner

    if app.is_itar or app.is_pci or app.is_hipaa:
        base_aws *= 1.15                       # GovCloud premium

    migration_cost = 2000 + volume * 0.1
    annual_savings = max((base_on_prem - base_aws) * 12, 0)

    return (
        round(base_aws, 2),
        round(base_on_prem, 2),
        round(migration_cost, 2),
        round(annual_savings, 2),
    )


# ─── Topological Sort (Dependency-Aware Wave Grouping) ───────────────────────

def _parse_deps(dep_str: Optional[str]) -> List[str]:
    if not dep_str:
        return []
    return [d.strip() for d in dep_str.split(",") if d.strip()]


def build_waves(apps: List[App]) -> Dict[int, List[App]]:
    """
    Group apps into ordered waves respecting dependencies.
    Returns dict: {wave_number (1-indexed): [apps]}.
    Uses Kahn's algorithm (topological sort BFS).
    """
    name_map: Dict[str, App] = {a.name: a for a in apps}
    in_degree: Dict[str, int] = {a.name: 0 for a in apps}
    adj: Dict[str, List[str]] = defaultdict(list)

    for app in apps:
        for dep in _parse_deps(app.dependencies):
            if dep in name_map:
                adj[dep].append(app.name)
                in_degree[app.name] = in_degree.get(app.name, 0) + 1

    queue = deque([a.name for a in apps if in_degree[a.name] == 0])
    wave_assignment: Dict[str, int] = {}
    wave_num = 1

    while queue:
        wave_members = list(queue)
        queue.clear()
        for name in wave_members:
            wave_assignment[name] = wave_num
            for successor in adj[name]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)
        wave_num += 1

    # Assign any unvisited apps (cycles) to their own wave
    for app in apps:
        if app.name not in wave_assignment:
            wave_assignment[app.name] = wave_num
            wave_num += 1

    waves: Dict[int, List[App]] = defaultdict(list)
    for app in apps:
        waves[wave_assignment[app.name]].append(app)

    return dict(sorted(waves.items()))


def generate_wave_dates(
    wave_number: int,
    wave_size: int,
    plan_start: date = None,
) -> Tuple[str, str]:
    """Return ISO-format start/end dates for a wave, spaced ~2 weeks apart."""
    if plan_start is None:
        plan_start = date.today() + timedelta(days=7)

    offset_days = (wave_number - 1) * 14
    start = plan_start + timedelta(days=offset_days)
    duration = max(7, min(wave_size * 2, 21))  # 7–21 days
    end = start + timedelta(days=duration)
    return start.isoformat(), end.isoformat()


# ─── Service Functions ───────────────────────────────────────────────────────

def classify_and_score_apps(db: Session, app_ids: Optional[List[int]] = None) -> List[App]:
    """Run classification, risk scoring, and cost estimation on all (or selected) apps."""
    query = db.query(App)
    if app_ids:
        query = query.filter(App.id.in_(app_ids))
    apps = query.all()

    for app in apps:
        app.migration_strategy = classify_strategy(app.tech_stack, app.data_volume_gb or 0)
        app.risk_score = compute_risk_score(app)
        monthly_aws, monthly_on_prem, migration_ot, savings = estimate_cost(app)
        app.estimated_cost_usd = monthly_aws

        # Upsert cost estimate
        ce = app.cost_estimate
        if ce is None:
            ce = CostEstimate(app_id=app.id)
            db.add(ce)
        ce.monthly_aws_cost = monthly_aws
        ce.monthly_on_prem_cost = monthly_on_prem
        ce.migration_one_time_cost = migration_ot
        ce.estimated_annual_savings = savings

    db.commit()
    return apps


def generate_plan(db: Session, plan_name: str, description: str = "") -> MigrationPlan:
    """
    Create a MigrationPlan, compute waves, assign apps to waves.
    Returns the saved MigrationPlan.
    """
    apps = db.query(App).all()
    if not apps:
        raise ValueError("No apps in inventory to plan.")

    # Classify first
    classify_and_score_apps(db)
    db.refresh_all = True  # refresh from DB

    apps = db.query(App).all()

    plan = MigrationPlan(
        name=plan_name,
        description=description,
        status="Active",
        total_apps=len(apps),
    )
    db.add(plan)
    db.flush()  # get plan.id

    wave_groups = build_waves(apps)
    total_cost = 0.0
    risk_scores = []

    for wave_num, wave_apps in wave_groups.items():
        start_date, end_date = generate_wave_dates(wave_num, len(wave_apps))
        wave_risk = round(sum(a.risk_score or 0 for a in wave_apps) / len(wave_apps), 2)

        wave = Wave(
            name=f"Wave {wave_num}",
            sequence=wave_num,
            start_date=start_date,
            end_date=end_date,
            risk_score=wave_risk,
            plan_id=plan.id,
            status="Planned",
        )
        db.add(wave)
        db.flush()

        for app in wave_apps:
            app.wave_id = wave.id
            app.status = "Planned"
            total_cost += app.estimated_cost_usd or 0
            risk_scores.append(app.risk_score or 0)

    plan.total_cost_usd = round(total_cost, 2)
    plan.overall_risk_score = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0
    db.commit()
    db.refresh(plan)
    return plan


def import_apps_from_csv(db: Session, csv_content: str) -> Tuple[int, int, List[str]]:
    """
    Parse CSV string and bulk-import Apps.
    Expected columns: name, tech_stack, region, data_sensitivity, sla_tier,
                      data_volume_gb, dependencies, is_itar, is_pci, is_hipaa
    Returns (imported_count, skipped_count, error_messages).
    """
    errors: List[str] = []
    imported = 0
    skipped = 0

    try:
        df = pd.read_csv(io.StringIO(csv_content))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    except Exception as e:
        return 0, 0, [f"CSV parse error: {e}"]

    required_cols = {"name"}
    if not required_cols.issubset(set(df.columns)):
        return 0, 0, ["CSV must have at least a 'name' column."]

    existing_names = {a.name for a in db.query(App.name).all()}

    for idx, row in df.iterrows():
        raw_name = row.get("name", "")
        name = "" if pd.isna(raw_name) else str(raw_name).strip()
        if not name:
            skipped += 1
            continue
        if name in existing_names:
            skipped += 1
            errors.append(f"Row {idx + 2}: app '{name}' already exists – skipped.")
            continue

        def _get(col: str, default=None):
            val = row.get(col, default)
            if pd.isna(val):
                return default
            return val

        app = App(
            name=name,
            tech_stack=_get("tech_stack"),
            region=_get("region", "us-east-1"),
            data_sensitivity=_get("data_sensitivity", "Low"),
            sla_tier=_get("sla_tier", "Standard"),
            data_volume_gb=float(_get("data_volume_gb", 0.0) or 0.0),
            dependencies=_get("dependencies"),
            is_itar=str(_get("is_itar", "false")).lower() in ("true", "1", "yes"),
            is_pci=str(_get("is_pci", "false")).lower() in ("true", "1", "yes"),
            is_hipaa=str(_get("is_hipaa", "false")).lower() in ("true", "1", "yes"),
        )
        db.add(app)
        existing_names.add(name)
        imported += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return 0, 0, [f"Database error: {e}"]

    _audit(db, action=f"Imported {imported} apps from CSV", resource_type="App")
    return imported, skipped, errors


def _audit(db: Session, action: str, resource_type: str = "", resource_id: str = ""):
    log = AuditLog(action=action, resource_type=resource_type, resource_id=resource_id)
    db.add(log)
    db.commit()
