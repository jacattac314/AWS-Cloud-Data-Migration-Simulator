"""Integration tests for the FastAPI backend endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.models.database import Base, get_db


# ─── Test DB Override ────────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="module")
def test_db_engine():
    # StaticPool ensures all connections reuse the same in-memory SQLite DB
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def client(test_db_engine):
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # lifespan=False skips the startup handler that calls create_tables() on the real engine
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Health Check ─────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ─── Migration App CRUD ───────────────────────────────────────────────────────

class TestAppCRUD:
    def test_create_app(self, client):
        r = client.post("/migration/apps", json={"name": "Test-App-001", "tech_stack": "Java Spring"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Test-App-001"
        assert "id" in data

    def test_list_apps(self, client):
        r = client.get("/migration/apps")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_app(self, client):
        create_r = client.post("/migration/apps", json={"name": "Test-App-002"})
        app_id = create_r.json()["id"]
        r = client.get(f"/migration/apps/{app_id}")
        assert r.status_code == 200
        assert r.json()["id"] == app_id

    def test_get_nonexistent_app_404(self, client):
        r = client.get("/migration/apps/999999")
        assert r.status_code == 404

    def test_update_app(self, client):
        create_r = client.post("/migration/apps", json={"name": "Test-App-Update"})
        app_id = create_r.json()["id"]
        r = client.patch(f"/migration/apps/{app_id}", json={"status": "In-Progress"})
        assert r.status_code == 200
        assert r.json()["status"] == "In-Progress"

    def test_delete_app(self, client):
        create_r = client.post("/migration/apps", json={"name": "Test-App-Delete"})
        app_id = create_r.json()["id"]
        r = client.delete(f"/migration/apps/{app_id}")
        assert r.status_code == 204
        r2 = client.get(f"/migration/apps/{app_id}")
        assert r2.status_code == 404


# ─── CSV Import ───────────────────────────────────────────────────────────────

class TestCSVImport:
    def test_import_valid_csv(self, client):
        csv_content = "name,tech_stack\nCSV-App-A,Node.js\nCSV-App-B,Python\n"
        r = client.post(
            "/migration/apps/import/csv",
            files={"file": ("apps.csv", csv_content.encode(), "text/csv")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["imported"] == 2

    def test_import_non_csv_rejected(self, client):
        r = client.post(
            "/migration/apps/import/csv",
            files={"file": ("apps.txt", b"content", "text/plain")},
        )
        assert r.status_code == 400


# ─── Classification ───────────────────────────────────────────────────────────

class TestClassification:
    def test_classify_endpoint(self, client):
        client.post("/migration/apps", json={"name": "Classify-Test", "tech_stack": "Java Tomcat"})
        r = client.post("/migration/apps/classify")
        assert r.status_code == 200
        apps = r.json()
        classify_test = next((a for a in apps if a["name"] == "Classify-Test"), None)
        assert classify_test is not None
        assert classify_test["migration_strategy"] in ("Rehost", "Replatform", "Refactor")


# ─── Knowledge Base ───────────────────────────────────────────────────────────

class TestKnowledgeBase:
    def test_create_entry(self, client):
        r = client.post(
            "/knowledge/entries",
            json={"title": "Test Entry", "content": "AWS migration runbook content.", "entry_type": "Runbook"},
        )
        assert r.status_code == 201
        data = r.json()
        assert len(data) > 0
        assert data[0]["title"].startswith("Test Entry")

    def test_list_entries(self, client):
        r = client.get("/knowledge/entries")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_search_returns_results(self, client):
        # Ingest something first
        client.post(
            "/knowledge/entries",
            json={"title": "EC2 Guide", "content": "EC2 rehost migration procedure step by step."},
        )
        r = client.post("/knowledge/search", json={"query": "EC2 migration", "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "query" in data

    def test_upload_text_file(self, client):
        content = b"This is a test runbook for migration procedures."
        r = client.post(
            "/knowledge/upload/text?title=Upload+Test&entry_type=Runbook",
            files={"file": ("test.txt", content, "text/plain")},
        )
        assert r.status_code == 201


# ─── Compliance ───────────────────────────────────────────────────────────────

class TestCompliance:
    def test_compliance_summary(self, client):
        r = client.get("/compliance/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_apps" in data
        assert "avg_compliance_score" in data

    def test_get_controls_for_itar_app(self, client):
        # Create an ITAR app
        create_r = client.post(
            "/migration/apps",
            json={"name": "ITAR-Test-App", "is_itar": True},
        )
        app_id = create_r.json()["id"]
        r = client.get(f"/compliance/apps/{app_id}/controls")
        assert r.status_code == 200
        controls = r.json()
        frameworks = {c["framework"] for c in controls}
        assert "ITAR" in frameworks

    def test_update_compliance_tags(self, client):
        create_r = client.post("/migration/apps", json={"name": "Compliance-Tag-Test"})
        app_id = create_r.json()["id"]
        r = client.patch(
            f"/compliance/apps/{app_id}/tags",
            params={"is_pci": True},
        )
        assert r.status_code == 200
        assert r.json()["is_pci"] is True

    def test_compliance_report(self, client):
        create_r = client.post(
            "/migration/apps",
            json={"name": "Report-Test-App", "is_hipaa": True},
        )
        app_id = create_r.json()["id"]
        r = client.get(f"/compliance/apps/{app_id}/report")
        assert r.status_code == 200
        data = r.json()
        assert data["app_id"] == app_id
        assert "HIPAA" in data["frameworks"]
        assert 0.0 <= data["compliance_score"] <= 100.0


# ─── Dashboard ────────────────────────────────────────────────────────────────

class TestDashboard:
    def test_metrics_endpoint(self, client):
        r = client.get("/dashboard/metrics")
        assert r.status_code == 200
        data = r.json()
        required_keys = [
            "total_apps", "apps_migrated", "migration_percent",
            "total_waves", "compliance_coverage_percent",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_strategy_distribution(self, client):
        r = client.get("/dashboard/migration/strategy-distribution")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_audit_logs(self, client):
        r = client.get("/dashboard/audit-logs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
