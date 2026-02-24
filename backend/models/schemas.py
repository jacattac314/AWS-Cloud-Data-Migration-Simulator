"""Pydantic v2 schemas for request/response validation."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ─── App Schemas ────────────────────────────────────────────────────────────

class AppBase(BaseModel):
    name: str
    tech_stack: Optional[str] = None
    region: Optional[str] = "us-east-1"
    data_sensitivity: Optional[str] = "Low"
    sla_tier: Optional[str] = "Standard"
    data_volume_gb: Optional[float] = 0.0
    dependencies: Optional[str] = None
    is_itar: Optional[bool] = False
    is_pci: Optional[bool] = False
    is_hipaa: Optional[bool] = False


class AppCreate(AppBase):
    pass


class AppUpdate(BaseModel):
    name: Optional[str] = None
    tech_stack: Optional[str] = None
    region: Optional[str] = None
    data_sensitivity: Optional[str] = None
    sla_tier: Optional[str] = None
    data_volume_gb: Optional[float] = None
    dependencies: Optional[str] = None
    migration_strategy: Optional[str] = None
    wave_id: Optional[int] = None
    status: Optional[str] = None
    is_itar: Optional[bool] = None
    is_pci: Optional[bool] = None
    is_hipaa: Optional[bool] = None


class AppResponse(AppBase):
    id: int
    migration_strategy: Optional[str] = None
    risk_score: Optional[float] = 0.0
    estimated_cost_usd: Optional[float] = 0.0
    status: Optional[str] = "Pending"
    wave_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Wave Schemas ────────────────────────────────────────────────────────────

class WaveBase(BaseModel):
    name: str
    sequence: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    risk_score: Optional[float] = 0.0
    status: Optional[str] = "Planned"


class WaveCreate(WaveBase):
    plan_id: Optional[int] = None


class WaveResponse(WaveBase):
    id: int
    plan_id: Optional[int] = None
    apps: List[AppResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Migration Plan Schemas ───────────────────────────────────────────────────

class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PlanResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    total_apps: int
    total_cost_usd: float
    overall_risk_score: float
    waves: List[WaveResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Knowledge Schemas ───────────────────────────────────────────────────────

class KnowledgeCreate(BaseModel):
    title: str
    content: str
    source_file: Optional[str] = None
    entry_type: Optional[str] = "Runbook"


class KnowledgeResponse(BaseModel):
    id: int
    title: str
    content: str
    source_file: Optional[str] = None
    entry_type: str
    chunk_index: int
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResult(BaseModel):
    entry: KnowledgeResponse
    score: float
    excerpt: str


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: List[KnowledgeSearchResult]
    answer: Optional[str] = None


# ─── Compliance Schemas ──────────────────────────────────────────────────────

class ComplianceControlResponse(BaseModel):
    id: int
    framework: str
    control_name: str
    description: Optional[str] = None
    is_implemented: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ComplianceUpdateRequest(BaseModel):
    control_id: int
    is_implemented: bool
    notes: Optional[str] = None


class ComplianceReportResponse(BaseModel):
    app_id: int
    app_name: str
    frameworks: List[str]
    controls: List[ComplianceControlResponse]
    compliance_score: float
    generated_at: datetime


# ─── Cost Schemas ────────────────────────────────────────────────────────────

class CostEstimateResponse(BaseModel):
    app_id: int
    monthly_aws_cost: float
    monthly_on_prem_cost: float
    migration_one_time_cost: float
    estimated_annual_savings: float
    actual_cost: Optional[float] = None
    currency: str = "USD"

    model_config = {"from_attributes": True}


# ─── Dashboard Schemas ───────────────────────────────────────────────────────

class DashboardMetrics(BaseModel):
    total_apps: int
    apps_migrated: int
    apps_in_progress: int
    apps_pending: int
    migration_percent: float
    total_waves: int
    waves_completed: int
    total_estimated_cost_usd: float
    total_estimated_savings_usd: float
    avg_risk_score: float
    compliance_coverage_percent: float
    itar_apps: int
    pci_apps: int
    hipaa_apps: int


class AuditLogResponse(BaseModel):
    id: int
    user: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


# ─── Import Schemas ──────────────────────────────────────────────────────────

class CSVImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: List[str] = []
    apps: List[AppResponse] = []
