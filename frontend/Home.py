"""Cloud Migration Command Center – Streamlit Home / Landing Page."""

import streamlit as st
import requests
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Cloud Migration Command Center",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .big-title { font-size: 2.8rem; font-weight: 800; color: #1e3a5f; margin-bottom: 0; }
    .sub-title { font-size: 1.2rem; color: #4a6fa5; margin-top: 0; }
    .card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        margin-bottom: 1rem;
    }
    .card h3 { color: #1e3a5f; margin-top: 0; }
    .metric-box {
        background: linear-gradient(135deg, #1e3a5f, #2d6a9f);
        border-radius: 10px;
        padding: 1.2rem;
        color: white;
        text-align: center;
    }
    .metric-box .value { font-size: 2.2rem; font-weight: 700; }
    .metric-box .label { font-size: 0.85rem; opacity: 0.85; }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def fetch_metrics():
    try:
        r = requests.get(f"{BACKEND_URL}/dashboard/metrics", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown('<p class="big-title">☁️ Cloud Migration Command Center</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-title">Enterprise-grade AWS migration planning, governance, and AI-powered operations</p>',
    unsafe_allow_html=True,
)
st.divider()

# ─── Live Metrics Banner ──────────────────────────────────────────────────────
metrics = fetch_metrics()
if metrics:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Apps", metrics["total_apps"])
    with col2:
        st.metric("Migrated", metrics["apps_migrated"], f"{metrics['migration_percent']}%")
    with col3:
        st.metric("Waves", metrics["total_waves"])
    with col4:
        st.metric("Est. Monthly Cost", f"${metrics['total_estimated_cost_usd']:,.0f}")
    with col5:
        st.metric("Compliance Coverage", f"{metrics['compliance_coverage_percent']}%")
else:
    st.info("Backend not yet running – start it with `uvicorn backend.main:app --reload` to see live metrics.", icon="ℹ️")

st.divider()

# ─── Feature Overview Cards ───────────────────────────────────────────────────
st.subheader("Platform Modules")
col_a, col_b = st.columns(2)

with col_a:
    st.markdown(
        """
        <div class="card">
        <h3>📋 Migration Planner</h3>
        <p>Upload your application inventory (CSV or manual entry). The system auto-classifies
        each app as <strong>Rehost</strong>, <strong>Replatform</strong>, or <strong>Refactor</strong>
        based on tech stack, then groups apps into dependency-aware migration waves with Gantt
        timeline, risk scoring, and cost estimation.</p>
        <ul>
          <li>Auto-classify via AWS 7-Rs heuristics</li>
          <li>Topological dependency-aware wave grouping</li>
          <li>Risk score &amp; TCO delta per app/wave</li>
          <li>CSV import / export</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_Migration_Planner.py", label="Open Migration Planner", icon="📋")

with col_b:
    st.markdown(
        """
        <div class="card">
        <h3>🧠 Knowledge-Led Ops (KLO)</h3>
        <p>Upload runbooks, SOPs, and ops guides. The KLO engine chunks and embeds content
        using OpenAI embeddings (or TF-IDF fallback), enabling semantic search.  Ask
        natural-language questions and receive AI-synthesized answers with source citations.</p>
        <ul>
          <li>Semantic search over operational docs</li>
          <li>OpenAI embeddings + TF-IDF fallback</li>
          <li>AI chat with contextual answers</li>
          <li>Auto-generate formatted runbooks</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/2_Knowledge_Base.py", label="Open Knowledge Base", icon="🧠")

col_c, col_d = st.columns(2)

with col_c:
    st.markdown(
        """
        <div class="card">
        <h3>🔐 Compliance Center</h3>
        <p>Tag apps with ITAR, PCI DSS, and HIPAA classifications. The Compliance Center
        surfaces the required AWS GovCloud controls, encryption requirements, audit logging
        mandates, and access restrictions for each framework.  Track implementation status
        and generate auditor-ready reports.</p>
        <ul>
          <li>ITAR / PCI DSS / HIPAA control checklists</li>
          <li>AWS GovCloud (US) simulation</li>
          <li>Per-app compliance score &amp; report</li>
          <li>CloudTrail-style audit log</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/3_Compliance_Center.py", label="Open Compliance Center", icon="🔐")

with col_d:
    st.markdown(
        """
        <div class="card">
        <h3>📊 Executive Dashboard</h3>
        <p>Real-time command view for leadership: migration velocity, cost savings, risk
        burn-down, wave timeline, and compliance posture in one unified pane.  All metrics
        update live from the planner and compliance modules.</p>
        <ul>
          <li>Migration progress &amp; velocity charts</li>
          <li>Cost &amp; savings KPIs</li>
          <li>Risk heatmap by wave</li>
          <li>Compliance posture summary</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/4_Executive_Dashboard.py", label="Open Executive Dashboard", icon="📊")

# ─── Architecture Overview ────────────────────────────────────────────────────
st.divider()
st.subheader("Architecture Overview")

arch_col, info_col = st.columns([2, 1])
with arch_col:
    st.code(
        """
 ┌─────────────────────────────────────────────────────────┐
 │           Cloud Migration Command Center                 │
 │                                                          │
 │  ┌──────────────┐    REST    ┌──────────────────────┐   │
 │  │  Streamlit   │◄──────────►│  FastAPI Backend     │   │
 │  │  Frontend    │            │  (Python 3.12)       │   │
 │  │  (4 modules) │            ├──────────────────────┤   │
 │  └──────────────┘            │  Migration Service   │   │
 │                              │  KLO / Embed Service │   │
 │  ┌──────────────┐            │  Compliance Service  │   │
 │  │  OpenAI API  │◄───────────│  Dashboard Service   │   │
 │  │  (Embeddings │            └──────────┬───────────┘   │
 │  │   + Chat)    │                       │               │
 │  └──────────────┘            ┌──────────▼───────────┐   │
 │                              │  SQLite / PostgreSQL  │   │
 │  ┌──────────────┐            │  (Apps, Waves, KLO,  │   │
 │  │  Terraform   │            │   Compliance, Audit) │   │
 │  │  Templates   │            └──────────────────────┘   │
 │  └──────────────┘                                        │
 └─────────────────────────────────────────────────────────┘
        """,
        language="text",
    )

with info_col:
    st.markdown("**Tech Stack**")
    st.markdown(
        """
        | Layer | Technology |
        |-------|-----------|
        | UI | Streamlit |
        | API | FastAPI |
        | ORM | SQLAlchemy 2 |
        | DB | SQLite / PostgreSQL |
        | AI/KLO | OpenAI + TF-IDF |
        | Infra | Terraform |
        | Containers | Docker / Compose |
        | CI/CD | GitHub Actions |
        """
    )

st.divider()
st.caption(
    "Cloud Migration Command Center · Portfolio Demo · "
    "Simulates enterprise AWS→data-center migration governance"
)
