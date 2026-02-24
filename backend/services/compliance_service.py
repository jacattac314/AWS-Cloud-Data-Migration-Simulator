"""Compliance Module service – control definitions, checklist management, audit reports."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.database import App, AuditLog, ComplianceControl

# ─── Control Definitions ──────────────────────────────────────────────────────
# Source: AWS ITAR/PCI/HIPAA documentation and AWS GovCloud FAQ

ITAR_CONTROLS: List[Dict] = [
    {
        "name": "Deploy in AWS GovCloud (US)",
        "description": (
            "All ITAR-controlled data must reside in AWS GovCloud (US) regions, which are "
            "physically isolated and restricted to US persons. "
            "(Ref: AWS GovCloud FAQ – data treated as ITAR by default.)"
        ),
    },
    {
        "name": "US-Only Personnel Access",
        "description": (
            "Only US persons (citizens, permanent residents) may access ITAR-controlled "
            "resources. Enforce via IAM policies and Cognito user attributes."
        ),
    },
    {
        "name": "Encryption at Rest (AWS KMS)",
        "description": (
            "Encrypt all data at rest using AWS KMS customer-managed keys (CMKs). "
            "Apply to S3 buckets, RDS instances, and EBS volumes."
        ),
    },
    {
        "name": "Encryption in Transit (TLS 1.2+)",
        "description": (
            "All network communication must use TLS 1.2 or higher. "
            "Enforce via ALB security policies and VPC endpoint policies."
        ),
    },
    {
        "name": "CloudTrail Audit Logging",
        "description": (
            "Enable AWS CloudTrail in all GovCloud regions for immutable audit logs. "
            "Store logs in an S3 bucket with Object Lock (WORM)."
        ),
    },
    {
        "name": "IAM Least-Privilege Policy",
        "description": (
            "Apply principle of least privilege: each service role has only the permissions "
            "required for its function. Review with IAM Access Analyzer."
        ),
    },
    {
        "name": "VPC Network Isolation",
        "description": (
            "Deploy ITAR workloads in a dedicated VPC with no public subnets. "
            "Use VPC endpoints for AWS service access."
        ),
    },
]

PCI_CONTROLS: List[Dict] = [
    {
        "name": "Cardholder Data Encryption (PCI DSS Req 3)",
        "description": (
            "Encrypt stored cardholder data using AES-256. "
            "Never store sensitive authentication data post-authorization."
        ),
    },
    {
        "name": "Network Segmentation (PCI DSS Req 1)",
        "description": (
            "Isolate cardholder data environment (CDE) with dedicated VPC, security groups, "
            "and NACLs. No direct internet access to CDE."
        ),
    },
    {
        "name": "Access Control (PCI DSS Req 7 & 8)",
        "description": (
            "Restrict access to cardholder data on need-to-know basis. "
            "Enforce MFA for all admin access. Use unique IDs per user."
        ),
    },
    {
        "name": "Vulnerability Management (PCI DSS Req 6)",
        "description": (
            "Apply security patches within 30 days. Run quarterly external vulnerability scans "
            "with an ASV. Maintain a secure development lifecycle."
        ),
    },
    {
        "name": "Logging & Monitoring (PCI DSS Req 10)",
        "description": (
            "Log all access to network resources and cardholder data. "
            "Use AWS Security Hub + CloudWatch for real-time alerting."
        ),
    },
    {
        "name": "Annual Penetration Test (PCI DSS Req 11)",
        "description": (
            "Conduct network and application penetration tests at least annually "
            "and after significant infrastructure changes."
        ),
    },
]

HIPAA_CONTROLS: List[Dict] = [
    {
        "name": "ePHI Encryption (HIPAA § 164.312)",
        "description": (
            "Encrypt all electronic Protected Health Information (ePHI) at rest and in transit "
            "using FIPS 140-2 validated algorithms (AES-256, TLS 1.2+)."
        ),
    },
    {
        "name": "Access Controls & Audit (HIPAA § 164.312(b))",
        "description": (
            "Implement role-based access controls for ePHI. Log all access, modification, "
            "and deletion events via CloudTrail and application-level audit logs."
        ),
    },
    {
        "name": "Business Associate Agreement (BAA)",
        "description": (
            "Execute a Business Associate Agreement with AWS before storing ePHI on any "
            "AWS service. AWS HIPAA-eligible services are listed in the AWS compliance guide."
        ),
    },
    {
        "name": "Backup & Disaster Recovery (HIPAA § 164.308(a)(7))",
        "description": (
            "Implement automated daily backups with cross-region replication. "
            "Test restore procedures quarterly. RTO < 4 h, RPO < 1 h for critical ePHI."
        ),
    },
    {
        "name": "Workforce Security Training",
        "description": (
            "Annual HIPAA security awareness training for all personnel with ePHI access. "
            "Document training completion in HR system."
        ),
    },
    {
        "name": "Breach Notification Procedure",
        "description": (
            "Maintain an incident response plan with < 60-day breach notification to HHS "
            "and affected individuals as required by HIPAA Breach Notification Rule."
        ),
    },
]

FRAMEWORK_CONTROLS: Dict[str, List[Dict]] = {
    "ITAR": ITAR_CONTROLS,
    "PCI": PCI_CONTROLS,
    "HIPAA": HIPAA_CONTROLS,
}


# ─── Service Functions ────────────────────────────────────────────────────────

def sync_controls_for_app(db: Session, app: App) -> List[ComplianceControl]:
    """
    Ensure the app has the correct compliance controls based on its tags.
    Adds missing controls; does NOT remove controls already marked as implemented.
    """
    needed_frameworks: List[str] = []
    if app.is_itar:
        needed_frameworks.append("ITAR")
    if app.is_pci:
        needed_frameworks.append("PCI")
    if app.is_hipaa:
        needed_frameworks.append("HIPAA")

    existing: Dict[str, ComplianceControl] = {
        f"{c.framework}::{c.control_name}": c
        for c in app.compliance_controls
    }

    for framework in needed_frameworks:
        for ctrl_def in FRAMEWORK_CONTROLS[framework]:
            key = f"{framework}::{ctrl_def['name']}"
            if key not in existing:
                ctrl = ComplianceControl(
                    app_id=app.id,
                    framework=framework,
                    control_name=ctrl_def["name"],
                    description=ctrl_def["description"],
                    is_implemented=False,
                )
                db.add(ctrl)

    # Remove controls for frameworks no longer applicable (only if NOT implemented)
    active_frameworks = set(needed_frameworks)
    for ctrl in list(app.compliance_controls):
        if ctrl.framework not in active_frameworks and not ctrl.is_implemented:
            db.delete(ctrl)

    db.commit()
    db.refresh(app)
    return app.compliance_controls


def update_compliance_flag(
    db: Session,
    app: App,
    is_itar: Optional[bool] = None,
    is_pci: Optional[bool] = None,
    is_hipaa: Optional[bool] = None,
) -> App:
    """Update compliance flags on an app and sync controls."""
    if is_itar is not None:
        app.is_itar = is_itar
    if is_pci is not None:
        app.is_pci = is_pci
    if is_hipaa is not None:
        app.is_hipaa = is_hipaa
    db.commit()
    sync_controls_for_app(db, app)
    _audit(db, f"Updated compliance flags for app '{app.name}'", "App", str(app.id))
    return app


def mark_control(
    db: Session,
    control_id: int,
    is_implemented: bool,
    notes: Optional[str] = None,
) -> Optional[ComplianceControl]:
    ctrl = db.query(ComplianceControl).filter(ComplianceControl.id == control_id).first()
    if not ctrl:
        return None
    ctrl.is_implemented = is_implemented
    if notes is not None:
        ctrl.notes = notes
    db.commit()
    _audit(
        db,
        f"Marked control '{ctrl.control_name}' as {'implemented' if is_implemented else 'pending'}",
        "ComplianceControl",
        str(control_id),
    )
    return ctrl


def get_compliance_score(app: App) -> float:
    """Return 0–100 compliance score based on % of controls implemented."""
    controls = app.compliance_controls
    if not controls:
        return 100.0  # no controls required
    implemented = sum(1 for c in controls if c.is_implemented)
    return round(100 * implemented / len(controls), 1)


def generate_compliance_report(db: Session, app: App) -> dict:
    """Build a structured compliance report for a single app."""
    controls = app.compliance_controls
    frameworks = []
    if app.is_itar:
        frameworks.append("ITAR")
    if app.is_pci:
        frameworks.append("PCI")
    if app.is_hipaa:
        frameworks.append("HIPAA")

    score = get_compliance_score(app)
    return {
        "app_id": app.id,
        "app_name": app.name,
        "frameworks": frameworks,
        "compliance_score": score,
        "total_controls": len(controls),
        "implemented_controls": sum(1 for c in controls if c.is_implemented),
        "pending_controls": [
            {"framework": c.framework, "control": c.control_name, "description": c.description}
            for c in controls
            if not c.is_implemented
        ],
        "implemented_list": [
            {"framework": c.framework, "control": c.control_name, "notes": c.notes}
            for c in controls
            if c.is_implemented
        ],
        "generated_at": datetime.utcnow().isoformat(),
        "deployment_note": (
            "Workload must be deployed in AWS GovCloud (US) due to ITAR classification."
            if app.is_itar else
            "Standard AWS commercial region deployment permitted."
        ),
    }


def _audit(db: Session, action: str, resource_type: str = "", resource_id: str = ""):
    log = AuditLog(action=action, resource_type=resource_type, resource_id=resource_id)
    db.add(log)
    db.commit()
