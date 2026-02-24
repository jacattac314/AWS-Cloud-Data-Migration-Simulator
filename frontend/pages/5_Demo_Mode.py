"""
Cloud Migration Command Center – Guided Demo Mode
Press through each step to walk a hiring manager (or any audience) through a
realistic enterprise migration scenario from zero to 100% migrated.
"""

import os
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Demo Mode – CMCC",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .demo-title  { font-size:2.6rem; font-weight:800; color:#1e3a5f; }
    .step-label  { font-size:1.05rem; font-weight:700; color:#4a6fa5; margin:0; }
    .narration   {
        background:#f0f7ff; border-left:4px solid #2563eb;
        padding:1rem 1.2rem; border-radius:6px;
        font-size:1.05rem; line-height:1.65;
    }
    .talking-pt  {
        background:#f0fdf4; border-left:4px solid #16a34a;
        padding:.9rem 1.2rem; border-radius:6px;
        font-size:.97rem; line-height:1.6;
    }
    .metric-card {
        background:linear-gradient(135deg,#1e3a5f,#2d6a9f);
        border-radius:10px; padding:1rem 1.2rem;
        color:white; text-align:center;
    }
    .metric-card .val { font-size:2rem; font-weight:700; }
    .metric-card .lbl { font-size:.78rem; opacity:.85; }
    .step-done   { color:#16a34a; }
    .step-active { color:#2563eb; font-weight:700; }
    .step-todo   { color:#9ca3af; }
    .badge {
        display:inline-block; padding:2px 10px;
        border-radius:9999px; font-size:.8rem; font-weight:600; color:white;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        font-size:1.1rem; padding:.65rem 2.2rem; border-radius:8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Demo Script ──────────────────────────────────────────────────────────────
# Each step: title, icon, narration, talking_points, action_label, action_fn

DEMO_CSV = """\
name,tech_stack,region,data_sensitivity,sla_tier,data_volume_gb,dependencies,is_itar,is_pci,is_hipaa
CRM-Service,Java Spring Boot,us-east-1,High,Premium,120,Auth-Service,false,false,false
Auth-Service,Node.js Express,us-east-1,Critical,Mission-Critical,5,,false,false,false
Payment-Gateway,Java Tomcat,us-east-1,Critical,Mission-Critical,30,Auth-Service,false,true,false
Patient-Portal,Django Python,us-east-1,High,Premium,200,Auth-Service,false,false,true
EHR-System,Legacy COBOL,us-east-1,Critical,Mission-Critical,800,Patient-Portal,false,false,true
BI-Dashboard,Node.js Express,us-east-1,Medium,Standard,15,CRM-Service,false,false,false
File-Server,Windows IIS,us-east-1,Medium,Standard,1500,,false,false,false
Email-Gateway,Postfix Linux,us-east-1,Low,Basic,10,,false,false,false
Defense-App,Java Tomcat,us-gov-west-1,Critical,Mission-Critical,50,Auth-Service,true,false,false
Inventory-Mgmt,PHP Laravel,us-east-1,Low,Standard,25,CRM-Service,false,false,false
Analytics-API,Python Flask,us-east-1,Medium,Standard,80,BI-Dashboard,false,false,false
Legacy-ERP,Monolith Java,us-east-1,High,Premium,300,CRM-Service,false,false,false
"""

DEMO_RUNBOOK = """\
# EC2 & RDS Migration Runbook

## Overview
Standard procedure for lifting EC2 instances and RDS databases from us-east-1
to target regions (including AWS GovCloud for ITAR workloads).

## Steps
1. Create AMI snapshot of source EC2 instance.
2. Copy AMI to target region with KMS encryption:
   aws ec2 copy-image --source-image-id ami-xxx --region us-gov-west-1 --encrypted
3. Launch new instance from copied AMI in target VPC.
4. For RDS: use AWS DMS for full-load + CDC replication.
5. Validate application health via smoke tests.
6. Update Route 53 / ALB target groups to cut over traffic.
7. Monitor CloudWatch metrics for 30 minutes post-cutover.

## ITAR Compliance Checklist
- Deploy only in us-gov-west-1 or us-gov-east-1.
- Use customer-managed KMS keys (CMKs) for all EBS and RDS encryption.
- Enable CloudTrail with S3 Object Lock for immutable audit trail.
- Restrict IAM access to US persons only.

## Rollback
1. Revert Route 53 to original instance IP.
2. Restart source instance if stopped.
3. File incident report in CMCC Audit Log.

## FAQ
Q: How long does a typical Rehost migration take?
A: 2–4 hours per instance including validation. Large databases (>1 TB) may need 8–24 hours via DMS.

Q: Can ITAR data go to AWS commercial regions?
A: No. ITAR data must remain in AWS GovCloud (US) at all times.
"""


def api(method: str, path: str, **kwargs):
    try:
        fn = getattr(requests, method)
        r = fn(f"{BACKEND}{path}", timeout=20, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach backend. Start it with: `uvicorn backend.main:app --reload`")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
        return None


def fetch_metrics():
    return api("get", "/dashboard/metrics") or {}


def fetch_apps():
    return api("get", "/migration/apps?limit=500") or []


def fetch_waves():
    return api("get", "/migration/waves") or []


# ─── Step Definitions ─────────────────────────────────────────────────────────

def step_reset():
    result = api("post", "/demo/reset")
    if result:
        st.session_state["demo_log"] = ["Demo environment reset – ready to begin."]
        return True
    return False


def step_load_inventory():
    result = api(
        "post",
        "/migration/apps/import/csv",
        files={"file": ("demo_apps.csv", DEMO_CSV.encode(), "text/csv")},
    )
    if result:
        st.session_state["demo_log"].append(
            f"Imported {result['imported']} applications into the migration inventory."
        )
        return True
    return False


def step_classify():
    result = api("post", "/migration/apps/classify")
    if result is not None:
        strategies = {}
        for a in result:
            s = a.get("migration_strategy", "Unknown")
            strategies[s] = strategies.get(s, 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in strategies.items())
        st.session_state["demo_log"].append(
            f"Classification complete: {summary}."
        )
        return True
    return False


def step_generate_plan():
    result = api(
        "post",
        "/migration/plans/generate",
        json={"name": "Q3 Data-Center Exit", "description": "Full migration of 12 enterprise apps"},
    )
    if result:
        n_waves = len(result.get("waves", []))
        st.session_state["demo_log"].append(
            f"Migration plan created: {n_waves} dependency-aware waves covering "
            f"{result['total_apps']} apps. Avg risk: {result['overall_risk_score']:.1f}/10."
        )
        st.session_state["plan_id"] = result["id"]
        return True
    return False


def step_compliance():
    apps = fetch_apps()
    tagged = 0
    for app in apps:
        if app.get("is_itar") or app.get("is_pci") or app.get("is_hipaa"):
            params = {
                "is_itar": app["is_itar"],
                "is_pci": app["is_pci"],
                "is_hipaa": app["is_hipaa"],
            }
            api("patch", f"/compliance/apps/{app['id']}/tags", params=params)
            tagged += 1
    st.session_state["demo_log"].append(
        f"Compliance controls applied to {tagged} regulated apps "
        f"(ITAR: Defense-App → GovCloud, PCI: Payment-Gateway, HIPAA: EHR-System & Patient-Portal)."
    )
    return True


def step_load_knowledge():
    result = api(
        "post",
        "/knowledge/upload/text?title=EC2+%26+RDS+Migration+Runbook&entry_type=Runbook",
        files={"file": ("demo_runbook.txt", DEMO_RUNBOOK.encode(), "text/plain")},
    )
    if result is not None:
        st.session_state["demo_log"].append(
            f"Ingested migration runbook into KLO engine ({len(result)} searchable chunks)."
        )
        return True
    return False


def _complete_wave(wave_number: int) -> bool:
    waves = fetch_waves()
    # Find the wave matching the sequence number that isn't yet completed
    target = next(
        (w for w in sorted(waves, key=lambda x: x["sequence"])
         if w["sequence"] == wave_number and w["status"] != "Completed"),
        None,
    )
    if not target:
        # Already done or no match – try first non-completed
        target = next((w for w in sorted(waves, key=lambda x: x["sequence"])
                       if w["status"] != "Completed"), None)
    if not target:
        st.session_state["demo_log"].append("All waves already completed.")
        return True
    result = api("patch", f"/migration/waves/{target['id']}", params={"status": "Completed"})
    if result:
        apps_in_wave = len(target.get("apps", []))
        st.session_state["demo_log"].append(
            f"{target['name']} migration complete — {apps_in_wave} apps moved to target infrastructure."
        )
        return True
    return False


STEPS = [
    {
        "title": "Welcome – Scenario Setup",
        "icon": "🏁",
        "narration": (
            "We're simulating a real enterprise scenario: migrating **12 production applications** "
            "out of an on-premises data center onto AWS. The portfolio spans Java microservices, "
            "a legacy COBOL ERP, regulated healthcare and defense workloads, and high-volume file servers. "
            "Click **Begin Demo** to initialize the environment."
        ),
        "talking_points": (
            "This mirrors the migration complexity I managed in real engagements — "
            "mixed tech stacks, compliance constraints, and dependency chains that determine "
            "sequencing. The Command Center is the single pane of glass that governs it all."
        ),
        "action_label": "Begin Demo",
        "action_fn": step_reset,
    },
    {
        "title": "Step 1 — Load App Inventory",
        "icon": "📥",
        "narration": (
            "The migration starts with **discovery**. We ingest the full application inventory: "
            "12 apps with their tech stacks, data volumes (5 GB → 1.5 TB), SLA tiers, "
            "inter-app dependencies, and compliance classifications. "
            "In production this would come from AWS Application Discovery Service or a CMDB export."
        ),
        "talking_points": (
            "Real projects always start with inventory. I've seen teams spend weeks just cataloguing "
            "what they have. With the CSV import here, you're going from zero to full visibility "
            "in seconds — that's the kind of velocity accelerator this tool provides."
        ),
        "action_label": "Import App Inventory",
        "action_fn": step_load_inventory,
    },
    {
        "title": "Step 2 — Auto-Classify Migration Strategy",
        "icon": "🤖",
        "narration": (
            "The engine analyses each app's tech stack against AWS's **7 Rs framework** and "
            "automatically assigns a migration strategy. Legacy COBOL → **Refactor**. "
            "Containerised Node.js → **Replatform**. Java Tomcat monoliths → **Rehost**. "
            "It also computes a **risk score** (0–10) and **monthly cost estimate** per app."
        ),
        "talking_points": (
            "This is the kind of analysis that normally takes a Solutions Architect a week to "
            "produce in a spreadsheet. The classification drives downstream planning, cost "
            "projections, and risk prioritisation — automatically, consistently, at scale."
        ),
        "action_label": "Run Auto-Classification",
        "action_fn": step_classify,
    },
    {
        "title": "Step 3 — Generate Migration Wave Plan",
        "icon": "🌊",
        "narration": (
            "The planner runs **Kahn's topological sort** on the dependency graph: "
            "Auth-Service (depended on by 4 apps) lands in Wave 1; CRM-Service and its "
            "downstream consumers follow in Wave 2; the high-risk Legacy-ERP and EHR-System "
            "move last with the most preparation. The Gantt timeline is generated automatically "
            "with 2-week windows per wave."
        ),
        "talking_points": (
            "Wave planning is where migrations succeed or fail. Move an app before its dependency "
            "and you get outages. This algorithm guarantees the correct order every time. "
            "The risk scores also let us surface which waves need the most change-management attention."
        ),
        "action_label": "Generate Wave Plan",
        "action_fn": step_generate_plan,
    },
    {
        "title": "Step 4 — Apply Compliance Controls",
        "icon": "🔐",
        "narration": (
            "The Compliance Engine tags regulated apps and materialises their required controls: "
            "**Defense-App** (ITAR) → must deploy in AWS GovCloud us-gov-west-1, KMS encryption, "
            "US-persons-only IAM; **Payment-Gateway** (PCI DSS) → cardholder data isolation, "
            "network segmentation, annual pen test; **EHR-System & Patient-Portal** (HIPAA) → "
            "ePHI encryption, BAA with AWS, breach notification plan."
        ),
        "talking_points": (
            "Compliance is the hardest part of regulated migrations. I've modelled these controls "
            "directly from the AWS GovCloud FAQ and PCI/HIPAA guidance. In an audit, you'd walk "
            "the auditor through this checklist — every control traced to its regulatory source."
        ),
        "action_label": "Apply Compliance Controls",
        "action_fn": step_compliance,
    },
    {
        "title": "Step 5 — Ingest Operational Runbooks (KLO)",
        "icon": "🧠",
        "narration": (
            "Before migrating, we load the operations team's runbooks into the **KLO engine**. "
            "The text is split into chunks, embedded using TF-IDF (or OpenAI when a key is "
            "configured), and indexed for semantic search. Engineers can now ask "
            "*'What's the rollback procedure for a failed EC2 migration?'* "
            "and get an AI-synthesised answer with citations."
        ),
        "talking_points": (
            "Knowledge-Led Operations is what separates mature migration programs from chaotic ones. "
            "When an on-call engineer at 2 AM hits a blocker, they shouldn't have to hunt through "
            "Confluence. This RAG pipeline surfaces the exact procedure in seconds."
        ),
        "action_label": "Load Runbooks into KLO",
        "action_fn": step_load_knowledge,
    },
    {
        "title": "Step 6 — Execute Wave 1 Migration",
        "icon": "🚀",
        "narration": (
            "**Wave 1** moves the foundational services: **Auth-Service** and **Email-Gateway** — "
            "the apps with no upstream dependencies. These are the lowest-risk, highest-leverage "
            "moves. Once Auth-Service is live on AWS, every downstream app can follow. "
            "The dashboard updates in real time as apps flip to Completed."
        ),
        "talking_points": (
            "In real migrations I always move shared services first to unblock everything else. "
            "Auth-Service here is the critical path — 4 other apps depend on it. "
            "Getting it stable in AWS first de-risks the entire program."
        ),
        "action_label": "Execute Wave 1",
        "action_fn": lambda: _complete_wave(1),
    },
    {
        "title": "Step 7 — Execute Wave 2 Migration",
        "icon": "🚀",
        "narration": (
            "**Wave 2** tackles the business-critical tier: **CRM-Service**, **Payment-Gateway**, "
            "and **Patient-Portal**. These carry PCI and HIPAA classifications — "
            "the Compliance Center ensures their AWS GovCloud controls are in place before "
            "cutover. Risk burn-down is visible on the dashboard."
        ),
        "talking_points": (
            "This is where compliance really earns its keep. Moving a PCI-scoped app without the "
            "right network segmentation and encryption in place is an audit finding waiting to happen. "
            "The checklist here ensures nothing ships without the required controls."
        ),
        "action_label": "Execute Wave 2",
        "action_fn": lambda: _complete_wave(2),
    },
    {
        "title": "Step 8 — Execute Remaining Waves",
        "icon": "🏁",
        "narration": (
            "Final waves complete the migration: the **Legacy-ERP** (Refactor — highest effort), "
            "**Defense-App** (ITAR → GovCloud), **File-Server** (1.5 TB data transfer), "
            "and analytics/BI tier. The Executive Dashboard now shows **100% migration complete**, "
            "cost savings realised, and full compliance coverage."
        ),
        "talking_points": (
            "The last wave is always the most complex — it's where the legacy debt lives. "
            "Having the risk score and compliance status visible throughout means leadership "
            "can see the program's health without needing a weekly status call. "
            "That's real-time governance."
        ),
        "action_label": "Complete All Remaining Waves",
        "action_fn": lambda: _complete_all_waves(),
    },
    {
        "title": "Migration Complete — Executive Summary",
        "icon": "🎉",
        "narration": (
            "The migration program is complete. All 12 applications are running on AWS. "
            "The Executive Dashboard shows live KPIs: migration velocity, total cost, "
            "estimated annual savings, risk burn-down, and compliance posture. "
            "Every action is captured in the immutable CloudTrail-style audit log. "
            "Export a PDF summary for the board."
        ),
        "talking_points": (
            "This is the outcome I delivered on the CruTrade and Zapata migrations — "
            "zero-downtime cutovers, full compliance documentation, and a live dashboard "
            "that executives could check at any time. The Command Center is the artefact "
            "that proves you ran a governed, measurable, repeatable migration program."
        ),
        "action_label": None,
        "action_fn": None,
    },
]


def _complete_all_waves():
    waves = fetch_waves()
    remaining = [w for w in waves if w["status"] != "Completed"]
    for wave in sorted(remaining, key=lambda x: x["sequence"]):
        api("patch", f"/migration/waves/{wave['id']}", params={"status": "Completed"})
    st.session_state["demo_log"].append(
        f"All {len(remaining)} remaining wave(s) marked complete. Data-center exit achieved."
    )
    return True


# ─── Session State Init ───────────────────────────────────────────────────────
if "demo_step" not in st.session_state:
    st.session_state["demo_step"] = 0
if "demo_log" not in st.session_state:
    st.session_state["demo_log"] = []
if "step_done" not in st.session_state:
    st.session_state["step_done"] = False

current_step = st.session_state["demo_step"]
total_steps = len(STEPS)
step = STEPS[current_step]


# ─── Header ───────────────────────────────────────────────────────────────────
header_col, reset_col = st.columns([5, 1])
with header_col:
    st.markdown('<p class="demo-title">🎬 Cloud Migration Command Center</p>', unsafe_allow_html=True)
    st.markdown(
        "<span style='color:#4a6fa5;font-size:1.1rem;'>Guided Demo — Hiring Manager Walkthrough</span>",
        unsafe_allow_html=True,
    )
with reset_col:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↺ Reset Demo", type="secondary", use_container_width=True):
        api("post", "/demo/reset")
        st.session_state["demo_step"] = 0
        st.session_state["demo_log"] = []
        st.session_state["step_done"] = False
        st.rerun()

# ─── Progress Bar ────────────────────────────────────────────────────────────
st.divider()
prog_cols = st.columns(total_steps)
for i, s in enumerate(STEPS):
    with prog_cols[i]:
        if i < current_step:
            css = "step-done"
            prefix = "✓"
        elif i == current_step:
            css = "step-active"
            prefix = "●"
        else:
            css = "step-todo"
            prefix = "○"
        st.markdown(
            f'<div style="text-align:center">'
            f'<span class="{css}" style="font-size:.8rem;">{prefix} {s["icon"]}</span><br>'
            f'<span style="font-size:.68rem;color:#6b7280;">{s["title"].split("—")[-1].strip()[:18]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown(
    f'<div style="margin:6px 0 2px;"><progress value="{current_step}" max="{total_steps - 1}" '
    f'style="width:100%;height:8px;"></progress></div>',
    unsafe_allow_html=True,
)
st.caption(f"Step {current_step + 1} of {total_steps}  ·  {step['title']}")

st.divider()

# ─── Main Layout: Step card (left) + Live Metrics (right) ────────────────────
left, right = st.columns([3, 2], gap="large")

with left:
    # Step title
    st.markdown(
        f'<p style="font-size:1.6rem;font-weight:800;color:#1e3a5f;margin-bottom:.3rem;">'
        f'{step["icon"]} {step["title"]}</p>',
        unsafe_allow_html=True,
    )

    # Narration
    st.markdown(
        f'<div class="narration">{step["narration"]}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Talking points
    st.markdown("**Talking point for hiring manager:**")
    st.markdown(
        f'<div class="talking-pt">💬 {step["talking_points"]}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Action button
    btn_col, nav_col = st.columns([2, 1])

    with btn_col:
        if step["action_label"] and not st.session_state["step_done"]:
            if st.button(
                f"▶  {step['action_label']}",
                type="primary",
                use_container_width=True,
                key=f"action_{current_step}",
            ):
                with st.spinner(f"Running: {step['action_label']}..."):
                    ok = step["action_fn"]()
                if ok:
                    st.session_state["step_done"] = True
                    st.rerun()
        elif st.session_state["step_done"] or step["action_label"] is None:
            if step["action_label"] is None:
                st.success("✅ Migration Complete!", icon="🎉")
            else:
                st.success(f"✅ {step['action_label']} — Done!", icon="✅")

    with nav_col:
        if st.session_state["step_done"] or step["action_label"] is None:
            if current_step < total_steps - 1:
                if st.button("Next Step →", type="primary", use_container_width=True):
                    st.session_state["demo_step"] += 1
                    st.session_state["step_done"] = False
                    st.rerun()
        if current_step > 0:
            if st.button("← Back", use_container_width=True):
                st.session_state["demo_step"] = max(0, current_step - 1)
                st.session_state["step_done"] = False
                st.rerun()

    # Activity log
    if st.session_state["demo_log"]:
        st.divider()
        st.markdown("**Activity Log**")
        for entry in reversed(st.session_state["demo_log"]):
            st.markdown(f"- {entry}")


# ─── Right Panel: Live Metrics ─────────────────────────────────────────────
with right:
    metrics = fetch_metrics()
    apps = fetch_apps()
    waves = api("get", "/dashboard/waves/breakdown") or []

    st.markdown("#### Live Dashboard Metrics")

    if not metrics or metrics.get("total_apps", 0) == 0:
        st.info("Metrics will appear once the inventory is loaded (Step 1).")
    else:
        # KPI grid
        r1c1, r1c2 = st.columns(2)
        r1c1.metric("Total Apps", metrics["total_apps"])
        r1c2.metric("Migrated", metrics["apps_migrated"], f"{metrics['migration_percent']:.0f}%")

        r2c1, r2c2 = st.columns(2)
        r2c1.metric("Waves Complete", f"{metrics['waves_completed']}/{metrics['total_waves']}")
        r2c2.metric("Avg Risk", f"{metrics['avg_risk_score']:.1f}/10")

        r3c1, r3c2 = st.columns(2)
        r3c1.metric("Est. Monthly Cost", f"${metrics['total_estimated_cost_usd']:,.0f}")
        r3c2.metric("Compliance", f"{metrics['compliance_coverage_percent']:.0f}%")

        st.markdown("")

        # Migration progress gauge
        pct = metrics["migration_percent"]
        fig_gauge = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=pct,
                title={"text": "Migration Complete", "font": {"size": 14}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1},
                    "bar": {"color": "#2563eb" if pct < 100 else "#16a34a"},
                    "steps": [
                        {"range": [0, 33], "color": "#fee2e2"},
                        {"range": [33, 66], "color": "#fef3c7"},
                        {"range": [66, 100], "color": "#d1fae5"},
                    ],
                    "threshold": {
                        "line": {"color": "#16a34a", "width": 3},
                        "thickness": 0.75,
                        "value": 100,
                    },
                },
                number={"suffix": "%", "font": {"size": 28}},
            )
        )
        fig_gauge.update_layout(height=200, margin=dict(t=30, b=10, l=20, r=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

        # Wave status bars (only show if waves exist)
        if waves:
            df_w = pd.DataFrame(waves)
            color_map = {
                "Planned": "#9ca3af",
                "In-Progress": "#f59e0b",
                "Completed": "#16a34a",
            }
            fig_waves = px.bar(
                df_w,
                x="wave_name",
                y="app_count",
                color="status",
                color_discrete_map=color_map,
                labels={"wave_name": "", "app_count": "Apps"},
                title="Wave Progress",
                text="app_count",
            )
            fig_waves.update_layout(
                height=220,
                showlegend=True,
                legend=dict(orientation="h", y=-0.3, x=0),
                margin=dict(t=35, b=10, l=10, r=10),
            )
            fig_waves.update_traces(textposition="outside")
            st.plotly_chart(fig_waves, use_container_width=True)

        # Compliance badges
        itar = metrics.get("itar_apps", 0)
        pci = metrics.get("pci_apps", 0)
        hipaa = metrics.get("hipaa_apps", 0)
        if itar or pci or hipaa:
            st.markdown(
                f'<span class="badge" style="background:#dc2626;">ITAR: {itar} app{"s" if itar!=1 else ""}</span> '
                f'<span class="badge" style="background:#d97706;">PCI: {pci} app{"s" if pci!=1 else ""}</span> '
                f'<span class="badge" style="background:#2563eb;">HIPAA: {hipaa} app{"s" if hipaa!=1 else ""}</span>',
                unsafe_allow_html=True,
            )

        # Strategy distribution (after classification)
        if apps:
            strategies = {}
            for a in apps:
                s = a.get("migration_strategy") or "Unclassified"
                strategies[s] = strategies.get(s, 0) + 1
            if len(strategies) > 1 or "Unclassified" not in strategies:
                fig_pie = px.pie(
                    names=list(strategies.keys()),
                    values=list(strategies.values()),
                    title="Strategy Mix",
                    color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b", "#9ca3af"],
                    hole=0.5,
                )
                fig_pie.update_layout(
                    height=200,
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.3),
                    margin=dict(t=35, b=10, l=10, r=10),
                )
                st.plotly_chart(fig_pie, use_container_width=True)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
fc1, fc2, fc3 = st.columns(3)
fc1.caption("☁️ Cloud Migration Command Center  |  Portfolio Demo")
fc2.caption(f"Step {current_step + 1}/{total_steps}  ·  {step['title']}")
fc3.caption("Backend: FastAPI + SQLAlchemy  ·  UI: Streamlit + Plotly")
