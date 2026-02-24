"""Unit tests for the Migration Planner service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.database import Base, App, Wave, MigrationPlan
from backend.services.migration_service import (
    classify_strategy,
    compute_risk_score,
    estimate_cost,
    build_waves,
    import_apps_from_csv,
    generate_plan,
)


# ─── Test DB Fixture ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ─── Classification Tests ─────────────────────────────────────────────────────

class TestClassifyStrategy:
    def test_rehost_generic(self):
        assert classify_strategy("Java Tomcat", 50) == "Rehost"

    def test_rehost_large_volume(self):
        # Large data volume should lean toward Rehost regardless of stack
        assert classify_strategy("Django Python", 600) == "Rehost"

    def test_replatform_spring(self):
        assert classify_strategy("Spring Boot Docker", 10) == "Replatform"

    def test_refactor_legacy(self):
        assert classify_strategy("Legacy COBOL Monolith", 200) == "Refactor"

    def test_refactor_mainframe(self):
        assert classify_strategy("IBM Mainframe AS400", 100) == "Refactor"

    def test_no_stack_defaults_rehost(self):
        assert classify_strategy(None, 0) == "Rehost"

    def test_empty_stack_defaults_rehost(self):
        assert classify_strategy("", 0) == "Rehost"


# ─── Risk Score Tests ─────────────────────────────────────────────────────────

class TestComputeRiskScore:
    def make_app(self, **kwargs) -> App:
        defaults = dict(
            data_sensitivity="Low",
            sla_tier="Standard",
            is_itar=False,
            is_pci=False,
            is_hipaa=False,
            migration_strategy="Rehost",
        )
        defaults.update(kwargs)
        app = App(id=1, name="test-app")
        for k, v in defaults.items():
            setattr(app, k, v)
        return app

    def test_low_risk_app(self):
        app = self.make_app()
        score = compute_risk_score(app)
        assert 0.0 <= score <= 3.0

    def test_itar_increases_risk(self):
        low = self.make_app(is_itar=False)
        high = self.make_app(is_itar=True)
        assert compute_risk_score(high) > compute_risk_score(low)

    def test_critical_sensitivity_increases_risk(self):
        low = self.make_app(data_sensitivity="Low")
        crit = self.make_app(data_sensitivity="Critical")
        assert compute_risk_score(crit) > compute_risk_score(low)

    def test_refactor_higher_than_rehost(self):
        rehost = self.make_app(migration_strategy="Rehost")
        refactor = self.make_app(migration_strategy="Refactor")
        assert compute_risk_score(refactor) > compute_risk_score(rehost)

    def test_score_bounded_to_10(self):
        app = self.make_app(
            data_sensitivity="Critical",
            sla_tier="Mission-Critical",
            is_itar=True,
            is_pci=True,
            is_hipaa=True,
            migration_strategy="Refactor",
        )
        assert compute_risk_score(app) <= 10.0


# ─── Cost Estimate Tests ──────────────────────────────────────────────────────

class TestEstimateCost:
    def make_app(self, **kwargs) -> App:
        app = App(id=1, name="test-app")
        app.data_volume_gb = kwargs.get("data_volume_gb", 0)
        app.migration_strategy = kwargs.get("migration_strategy", "Rehost")
        app.is_itar = kwargs.get("is_itar", False)
        app.is_pci = kwargs.get("is_pci", False)
        app.is_hipaa = kwargs.get("is_hipaa", False)
        return app

    def test_returns_four_values(self):
        app = self.make_app()
        result = estimate_cost(app)
        assert len(result) == 4

    def test_all_values_non_negative(self):
        app = self.make_app(data_volume_gb=100)
        monthly_aws, monthly_on_prem, migration_cost, savings = estimate_cost(app)
        assert monthly_aws >= 0
        assert monthly_on_prem >= 0
        assert migration_cost >= 0
        assert savings >= 0

    def test_itar_premium(self):
        no_itar = self.make_app(is_itar=False)
        with_itar = self.make_app(is_itar=True)
        aws_no, *_ = estimate_cost(no_itar)
        aws_yes, *_ = estimate_cost(with_itar)
        assert aws_yes > aws_no

    def test_larger_volume_costs_more(self):
        small = self.make_app(data_volume_gb=10)
        large = self.make_app(data_volume_gb=1000)
        cost_small, *_ = estimate_cost(small)
        cost_large, *_ = estimate_cost(large)
        assert cost_large > cost_small


# ─── Wave Grouping Tests ──────────────────────────────────────────────────────

class TestBuildWaves:
    def make_app(self, name: str, deps: str = "") -> App:
        a = App(name=name)
        a.dependencies = deps or None
        return a

    def test_no_deps_all_in_wave_1(self):
        apps = [self.make_app("A"), self.make_app("B"), self.make_app("C")]
        waves = build_waves(apps)
        assert 1 in waves
        assert len(waves[1]) == 3

    def test_dep_creates_two_waves(self):
        apps = [self.make_app("A"), self.make_app("B", deps="A")]
        waves = build_waves(apps)
        wave_1_names = {a.name for a in waves[1]}
        wave_2_names = {a.name for a in waves[2]}
        assert "A" in wave_1_names
        assert "B" in wave_2_names

    def test_chain_creates_three_waves(self):
        apps = [
            self.make_app("A"),
            self.make_app("B", deps="A"),
            self.make_app("C", deps="B"),
        ]
        waves = build_waves(apps)
        assert len(waves) == 3

    def test_unknown_dep_ignored(self):
        apps = [self.make_app("A", deps="NonExistentApp")]
        waves = build_waves(apps)
        assert "A" in {a.name for a in waves[1]}

    def test_multiple_deps(self):
        apps = [
            self.make_app("A"),
            self.make_app("B"),
            self.make_app("C", deps="A, B"),
        ]
        waves = build_waves(apps)
        wave_1_names = {a.name for a in waves[1]}
        assert "A" in wave_1_names
        assert "B" in wave_1_names
        assert "C" not in wave_1_names


# ─── CSV Import Tests ─────────────────────────────────────────────────────────

class TestCSVImport:
    VALID_CSV = """name,tech_stack,region,data_sensitivity
App-Alpha,Java Spring,us-east-1,High
App-Beta,Python Flask,us-east-1,Low
"""

    DUPLICATE_CSV = """name,tech_stack
App-Alpha,Java Spring
"""

    def test_import_valid(self, db):
        imported, skipped, errors = import_apps_from_csv(db, self.VALID_CSV)
        assert imported == 2
        assert skipped == 0
        assert errors == []

    def test_import_persists_to_db(self, db):
        import_apps_from_csv(db, self.VALID_CSV)
        apps = db.query(App).all()
        names = {a.name for a in apps}
        assert "App-Alpha" in names
        assert "App-Beta" in names

    def test_duplicate_skipped(self, db):
        import_apps_from_csv(db, self.VALID_CSV)
        imported, skipped, errors = import_apps_from_csv(db, self.DUPLICATE_CSV)
        assert imported == 0
        assert skipped == 1
        assert len(errors) == 1

    def test_missing_name_column(self, db):
        csv = "tech_stack,region\nJava,us-east-1"
        imported, skipped, errors = import_apps_from_csv(db, csv)
        assert imported == 0
        assert any("name" in e.lower() for e in errors)

    def test_empty_name_skipped(self, db):
        csv = "name,tech_stack\n,Java\nGoodApp,Python"
        imported, skipped, errors = import_apps_from_csv(db, csv)
        assert imported == 1
        assert skipped == 1

    def test_compliance_flags_parsed(self, db):
        csv = "name,is_itar,is_pci,is_hipaa\nSecureApp,true,false,yes"
        import_apps_from_csv(db, csv)
        app = db.query(App).filter(App.name == "SecureApp").first()
        assert app.is_itar is True
        assert app.is_pci is False
        assert app.is_hipaa is True
