"""Unit tests for the Compliance Module service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.database import App, Base, ComplianceControl
from backend.services.compliance_service import (
    FRAMEWORK_CONTROLS,
    get_compliance_score,
    generate_compliance_report,
    mark_control,
    sync_controls_for_app,
    update_compliance_flag,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def basic_app(db):
    app = App(name="TestApp", is_itar=False, is_pci=False, is_hipaa=False)
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


class TestFrameworkDefinitions:
    def test_itar_controls_defined(self):
        assert len(FRAMEWORK_CONTROLS["ITAR"]) >= 5

    def test_pci_controls_defined(self):
        assert len(FRAMEWORK_CONTROLS["PCI"]) >= 4

    def test_hipaa_controls_defined(self):
        assert len(FRAMEWORK_CONTROLS["HIPAA"]) >= 4

    def test_itar_includes_govcloud(self):
        names = [c["name"] for c in FRAMEWORK_CONTROLS["ITAR"]]
        assert any("GovCloud" in n for n in names)

    def test_itar_includes_kms(self):
        names = [c["name"] for c in FRAMEWORK_CONTROLS["ITAR"]]
        assert any("KMS" in n for n in names)

    def test_pci_includes_encryption(self):
        names = [c["name"] for c in FRAMEWORK_CONTROLS["PCI"]]
        assert any("Encrypt" in n for n in names)

    def test_hipaa_includes_phi(self):
        names = [c["name"] for c in FRAMEWORK_CONTROLS["HIPAA"]]
        assert any("PHI" in n or "ePHI" in n for n in names)


class TestSyncControls:
    def test_no_frameworks_no_controls(self, db, basic_app):
        sync_controls_for_app(db, basic_app)
        assert len(basic_app.compliance_controls) == 0

    def test_itar_tag_creates_controls(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        fw_names = {c.framework for c in basic_app.compliance_controls}
        assert "ITAR" in fw_names
        assert len(basic_app.compliance_controls) == len(FRAMEWORK_CONTROLS["ITAR"])

    def test_pci_tag_creates_pci_controls(self, db, basic_app):
        basic_app.is_pci = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        fw_names = {c.framework for c in basic_app.compliance_controls}
        assert "PCI" in fw_names

    def test_multiple_frameworks(self, db, basic_app):
        basic_app.is_itar = True
        basic_app.is_pci = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        fw_names = {c.framework for c in basic_app.compliance_controls}
        assert "ITAR" in fw_names
        assert "PCI" in fw_names
        expected_count = len(FRAMEWORK_CONTROLS["ITAR"]) + len(FRAMEWORK_CONTROLS["PCI"])
        assert len(basic_app.compliance_controls) == expected_count

    def test_idempotent(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        count_after_first = len(basic_app.compliance_controls)
        sync_controls_for_app(db, basic_app)
        count_after_second = len(basic_app.compliance_controls)
        assert count_after_first == count_after_second

    def test_removing_framework_removes_pending_controls(self, db, basic_app):
        basic_app.is_pci = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        assert any(c.framework == "PCI" for c in basic_app.compliance_controls)

        basic_app.is_pci = False
        db.commit()
        sync_controls_for_app(db, basic_app)
        assert not any(c.framework == "PCI" for c in basic_app.compliance_controls)


class TestUpdateFlags:
    def test_set_itar_flag(self, db, basic_app):
        updated = update_compliance_flag(db, basic_app, is_itar=True)
        assert updated.is_itar is True

    def test_controls_created_after_flag_set(self, db, basic_app):
        update_compliance_flag(db, basic_app, is_itar=True)
        db.refresh(basic_app)
        assert len(basic_app.compliance_controls) > 0

    def test_partial_update(self, db, basic_app):
        update_compliance_flag(db, basic_app, is_hipaa=True)
        assert basic_app.is_hipaa is True
        assert basic_app.is_itar is False  # unchanged


class TestMarkControl:
    def test_mark_implemented(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        ctrl = basic_app.compliance_controls[0]
        result = mark_control(db, ctrl.id, True, "Enabled via Terraform")
        assert result.is_implemented is True
        assert result.notes == "Enabled via Terraform"

    def test_mark_not_found_returns_none(self, db):
        result = mark_control(db, 99999, True)
        assert result is None

    def test_mark_then_unmark(self, db, basic_app):
        basic_app.is_pci = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        ctrl = basic_app.compliance_controls[0]
        mark_control(db, ctrl.id, True)
        mark_control(db, ctrl.id, False)
        db.refresh(ctrl)
        assert ctrl.is_implemented is False


class TestComplianceScore:
    def test_no_controls_score_100(self, db, basic_app):
        assert get_compliance_score(basic_app) == 100.0

    def test_all_pending_score_0(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        assert get_compliance_score(basic_app) == 0.0

    def test_half_implemented_score_50(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        controls = basic_app.compliance_controls
        half = len(controls) // 2
        for ctrl in controls[:half]:
            mark_control(db, ctrl.id, True)
        db.refresh(basic_app)
        score = get_compliance_score(basic_app)
        assert 40.0 <= score <= 60.0


class TestComplianceReport:
    def test_report_structure(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        report = generate_compliance_report(db, basic_app)
        assert report["app_id"] == basic_app.id
        assert report["app_name"] == basic_app.name
        assert "ITAR" in report["frameworks"]
        assert "compliance_score" in report
        assert "pending_controls" in report
        assert "implemented_list" in report

    def test_itar_report_mentions_govcloud(self, db, basic_app):
        basic_app.is_itar = True
        db.commit()
        sync_controls_for_app(db, basic_app)
        report = generate_compliance_report(db, basic_app)
        assert "GovCloud" in report["deployment_note"]

    def test_non_itar_report_allows_commercial(self, db, basic_app):
        report = generate_compliance_report(db, basic_app)
        assert "commercial" in report["deployment_note"].lower()
