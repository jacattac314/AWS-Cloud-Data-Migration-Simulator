"""Migration Planner page – upload apps, classify, plan waves, view timeline."""

import io
import os
from datetime import date, timedelta
from typing import List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Migration Planner", page_icon="📋", layout="wide")
st.title("📋 Migration Planner")
st.caption("Upload your app inventory, auto-classify migration strategies, and generate wave plans.")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{BACKEND}{path}", timeout=15, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is the API server running?")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e.response.status_code} – {e.response.text}")
        return None


def display_apps_table(apps: List[dict]):
    if not apps:
        st.info("No apps in inventory yet.")
        return
    df = pd.DataFrame(apps)
    display_cols = [
        "id", "name", "tech_stack", "region", "data_sensitivity",
        "migration_strategy", "risk_score", "estimated_cost_usd",
        "status", "wave_id", "is_itar", "is_pci", "is_hipaa",
    ]
    df = df[[c for c in display_cols if c in df.columns]]
    df.rename(
        columns={
            "tech_stack": "Tech Stack",
            "data_sensitivity": "Sensitivity",
            "migration_strategy": "Strategy",
            "risk_score": "Risk",
            "estimated_cost_usd": "Est. Cost/mo ($)",
            "wave_id": "Wave",
            "is_itar": "ITAR",
            "is_pci": "PCI",
            "is_hipaa": "HIPAA",
        },
        inplace=True,
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


# ─── Sidebar Actions ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Actions")

    st.subheader("Import Apps")
    uploaded_csv = st.file_uploader("Upload CSV", type=["csv"], key="csv_upload")
    if uploaded_csv and st.button("Import CSV", type="primary"):
        result = api(
            "post",
            "/migration/apps/import/csv",
            files={"file": (uploaded_csv.name, uploaded_csv.read(), "text/csv")},
        )
        if result:
            st.success(f"Imported {result['imported']} apps, skipped {result['skipped']}.")
            if result["errors"]:
                for e in result["errors"][:5]:
                    st.warning(e)
            st.rerun()

    st.divider()
    st.subheader("Sample Data")
    if st.button("Load Demo Apps"):
        demo_csv = """name,tech_stack,region,data_sensitivity,sla_tier,data_volume_gb,dependencies,is_itar,is_pci,is_hipaa
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
        result = api(
            "post",
            "/migration/apps/import/csv",
            files={"file": ("demo.csv", demo_csv.encode(), "text/csv")},
        )
        if result:
            st.success(f"Loaded {result['imported']} demo apps.")
            st.rerun()

    st.divider()
    if st.button("Auto-Classify All Apps"):
        result = api("post", "/migration/apps/classify")
        if result is not None:
            st.success(f"Classified {len(result)} apps.")
            st.rerun()


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_inventory, tab_add, tab_plan, tab_timeline = st.tabs(
    ["App Inventory", "Add App", "Generate Plan", "Wave Timeline"]
)

# ─── Tab 1: Inventory ─────────────────────────────────────────────────────────
with tab_inventory:
    st.subheader("Application Inventory")
    apps = api("get", "/migration/apps") or []
    display_apps_table(apps)

    if apps:
        st.divider()
        col_strat, col_risk = st.columns(2)
        df_apps = pd.DataFrame(apps)

        with col_strat:
            if "migration_strategy" in df_apps.columns:
                strat_counts = df_apps["migration_strategy"].value_counts().reset_index()
                strat_counts.columns = ["Strategy", "Count"]
                fig = px.pie(
                    strat_counts,
                    names="Strategy",
                    values="Count",
                    title="Migration Strategy Distribution",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    hole=0.4,
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_risk:
            if "risk_score" in df_apps.columns and "name" in df_apps.columns:
                df_sorted = df_apps.nlargest(10, "risk_score")
                fig2 = px.bar(
                    df_sorted,
                    x="name",
                    y="risk_score",
                    color="risk_score",
                    color_continuous_scale="RdYlGn_r",
                    title="Top 10 Apps by Risk Score",
                    labels={"name": "App", "risk_score": "Risk Score"},
                )
                fig2.update_layout(xaxis_tickangle=-30)
                st.plotly_chart(fig2, use_container_width=True)


# ─── Tab 2: Add App Manually ──────────────────────────────────────────────────
with tab_add:
    st.subheader("Add Application Manually")
    with st.form("add_app_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("App Name *", placeholder="e.g. Payment-Gateway")
            tech_stack = st.text_input("Tech Stack", placeholder="e.g. Java Spring Boot")
            region = st.selectbox(
                "AWS Region",
                ["us-east-1", "us-east-2", "us-west-1", "us-west-2", "us-gov-west-1", "us-gov-east-1"],
            )
            data_sensitivity = st.selectbox("Data Sensitivity", ["Low", "Medium", "High", "Critical"])
        with c2:
            sla_tier = st.selectbox("SLA Tier", ["Basic", "Standard", "Premium", "Mission-Critical"])
            data_volume_gb = st.number_input("Data Volume (GB)", min_value=0.0, value=0.0, step=10.0)
            dependencies = st.text_input(
                "Dependencies (comma-separated app names)",
                placeholder="Auth-Service, DB-Cluster",
            )
            c_itar, c_pci, c_hipaa = st.columns(3)
            is_itar = c_itar.checkbox("ITAR")
            is_pci = c_pci.checkbox("PCI")
            is_hipaa = c_hipaa.checkbox("HIPAA")

        submitted = st.form_submit_button("Add App", type="primary")
        if submitted:
            if not name.strip():
                st.error("App Name is required.")
            else:
                result = api(
                    "post",
                    "/migration/apps",
                    json={
                        "name": name.strip(),
                        "tech_stack": tech_stack or None,
                        "region": region,
                        "data_sensitivity": data_sensitivity,
                        "sla_tier": sla_tier,
                        "data_volume_gb": data_volume_gb,
                        "dependencies": dependencies or None,
                        "is_itar": is_itar,
                        "is_pci": is_pci,
                        "is_hipaa": is_hipaa,
                    },
                )
                if result:
                    st.success(f"App '{result['name']}' added (ID: {result['id']}).")
                    st.rerun()


# ─── Tab 3: Generate Plan ─────────────────────────────────────────────────────
with tab_plan:
    st.subheader("Generate Migration Plan")
    apps_count = len(api("get", "/migration/apps") or [])
    st.info(f"Currently **{apps_count}** apps in inventory. The planner will group them into dependency-aware waves.")

    with st.form("gen_plan_form"):
        plan_name = st.text_input("Plan Name", value=f"Migration Plan {date.today().isoformat()}")
        plan_desc = st.text_area("Description (optional)", placeholder="Q3 data-center exit...")
        gen_btn = st.form_submit_button("Generate Plan", type="primary")

        if gen_btn:
            if apps_count == 0:
                st.error("Add apps to the inventory before generating a plan.")
            else:
                with st.spinner("Classifying apps and building wave groups..."):
                    plan = api(
                        "post",
                        "/migration/plans/generate",
                        json={"name": plan_name, "description": plan_desc},
                    )
                if plan:
                    st.success(
                        f"Plan **{plan['name']}** created with **{len(plan['waves'])}** waves "
                        f"covering {plan['total_apps']} apps."
                    )
                    st.session_state["active_plan"] = plan

    # Show existing plans
    plans = api("get", "/migration/plans") or []
    if plans:
        st.divider()
        st.subheader("Saved Plans")
        for p in plans:
            with st.expander(f"📅 {p['name']} – {len(p['waves'])} waves, {p['total_apps']} apps"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Apps", p["total_apps"])
                col2.metric("Est. Monthly Cost", f"${p['total_cost_usd']:,.0f}")
                col3.metric("Avg Risk Score", p["overall_risk_score"])

                for wave in sorted(p["waves"], key=lambda w: w["sequence"]):
                    status_color = {
                        "Completed": "green",
                        "In-Progress": "orange",
                        "Planned": "blue",
                    }.get(wave["status"], "grey")
                    st.markdown(
                        f"**{wave['name']}** — {len(wave['apps'])} apps — "
                        f"Risk: {wave['risk_score']} — "
                        f":{status_color}[{wave['status']}] — "
                        f"{wave.get('start_date', '?')} → {wave.get('end_date', '?')}"
                    )


# ─── Tab 4: Wave Timeline ─────────────────────────────────────────────────────
with tab_timeline:
    st.subheader("Wave Gantt Timeline")
    waves = api("get", "/migration/waves") or []

    if not waves:
        st.info("No waves yet – generate a plan first.")
    else:
        # Build Gantt data
        gantt_rows = []
        for w in waves:
            start = w.get("start_date") or date.today().isoformat()
            end = w.get("end_date") or (date.today() + timedelta(days=14)).isoformat()
            for app in w.get("apps", []):
                gantt_rows.append({
                    "Wave": w["name"],
                    "App": app["name"],
                    "Start": start,
                    "End": end,
                    "Status": w["status"],
                    "Risk": app.get("risk_score", 0),
                })

        if gantt_rows:
            df_gantt = pd.DataFrame(gantt_rows)
            fig = px.timeline(
                df_gantt,
                x_start="Start",
                x_end="End",
                y="Wave",
                color="Status",
                hover_name="App",
                hover_data={"Risk": True},
                title="Migration Wave Timeline",
                color_discrete_map={
                    "Planned": "#4a90e2",
                    "In-Progress": "#f5a623",
                    "Completed": "#7ed321",
                },
            )
            fig.update_yaxes(autorange="reversed")
            fig.update_layout(height=max(350, len(waves) * 60))
            st.plotly_chart(fig, use_container_width=True)

            # Wave status control
            st.subheader("Update Wave Status")
            wave_names = {w["name"]: w["id"] for w in waves}
            sel_wave_name = st.selectbox("Select Wave", list(wave_names.keys()))
            new_status = st.selectbox("New Status", ["Planned", "In-Progress", "Completed"])
            if st.button("Update Status"):
                result = api(
                    "patch",
                    f"/migration/waves/{wave_names[sel_wave_name]}",
                    params={"status": new_status},
                )
                if result:
                    st.success(f"{sel_wave_name} status updated to {new_status}.")
                    st.rerun()
        else:
            st.info("Waves have no apps yet.")
