"""SQLAlchemy ORM models for the Cloud Migration Command Center."""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from backend.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class App(Base):
    """Represents an application or server in the migration inventory."""
    __tablename__ = "apps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    tech_stack = Column(String(255), nullable=True)
    region = Column(String(100), nullable=True, default="us-east-1")
    data_sensitivity = Column(String(50), nullable=True, default="Low")
    sla_tier = Column(String(50), nullable=True, default="Standard")
    data_volume_gb = Column(Float, nullable=True, default=0.0)
    dependencies = Column(Text, nullable=True)          # comma-separated app names
    migration_strategy = Column(String(50), nullable=True)  # Rehost / Replatform / Refactor
    risk_score = Column(Float, nullable=True, default=0.0)
    estimated_cost_usd = Column(Float, nullable=True, default=0.0)
    status = Column(String(50), nullable=True, default="Pending")

    # Compliance flags
    is_itar = Column(Boolean, default=False)
    is_pci = Column(Boolean, default=False)
    is_hipaa = Column(Boolean, default=False)

    wave_id = Column(Integer, ForeignKey("waves.id"), nullable=True)
    wave = relationship("Wave", back_populates="apps")
    compliance_controls = relationship("ComplianceControl", back_populates="app", cascade="all, delete-orphan")
    cost_estimate = relationship("CostEstimate", back_populates="app", uselist=False, cascade="all, delete-orphan")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MigrationPlan(Base):
    """A named migration plan containing multiple waves."""
    __tablename__ = "migration_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="Draft")  # Draft, Active, Completed
    total_apps = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    overall_risk_score = Column(Float, default=0.0)

    waves = relationship("Wave", back_populates="plan", cascade="all, delete-orphan")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Wave(Base):
    """A migration wave – a batch of apps moved together."""
    __tablename__ = "waves"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    sequence = Column(Integer, nullable=False, default=1)
    start_date = Column(String(20), nullable=True)
    end_date = Column(String(20), nullable=True)
    risk_score = Column(Float, default=0.0)
    status = Column(String(50), default="Planned")  # Planned, In-Progress, Completed

    plan_id = Column(Integer, ForeignKey("migration_plans.id"), nullable=True)
    plan = relationship("MigrationPlan", back_populates="waves")
    apps = relationship("App", back_populates="wave")

    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeEntry(Base):
    """A chunk of operational knowledge (runbook, FAQ, etc.)."""
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    source_file = Column(String(255), nullable=True)
    entry_type = Column(String(50), default="Runbook")  # Runbook, FAQ, Incident, General
    chunk_index = Column(Integer, default=0)
    embedding_json = Column(Text, nullable=True)        # JSON-serialized embedding vector

    created_at = Column(DateTime, default=datetime.utcnow)


class ComplianceControl(Base):
    """A compliance control requirement for a specific app."""
    __tablename__ = "compliance_controls"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("apps.id"), nullable=False)
    framework = Column(String(50), nullable=False)      # ITAR, PCI, HIPAA
    control_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_implemented = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    app = relationship("App", back_populates="compliance_controls")
    created_at = Column(DateTime, default=datetime.utcnow)


class CostEstimate(Base):
    """Per-app cost projection."""
    __tablename__ = "cost_estimates"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("apps.id"), nullable=False, unique=True)
    monthly_aws_cost = Column(Float, default=0.0)
    monthly_on_prem_cost = Column(Float, default=0.0)
    migration_one_time_cost = Column(Float, default=0.0)
    estimated_annual_savings = Column(Float, default=0.0)
    actual_cost = Column(Float, nullable=True)
    currency = Column(String(10), default="USD")

    app = relationship("App", back_populates="cost_estimate")
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Immutable audit trail of user actions (CloudTrail-style)."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user = Column(String(100), default="system")
    action = Column(String(255), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


def get_db():
    """FastAPI dependency that provides a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables (idempotent)."""
    Base.metadata.create_all(bind=engine)
