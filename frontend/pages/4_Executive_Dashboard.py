"""Executive Dashboard – real-time migration KPIs, charts, and risk heatmap."""

import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Executive Dashboard", page_icon="📊", layout="wide")
st.title("📊 Executive Dashboard")
st.caption("Command-level view of migration progress, cost, risk, and compliance posture.")


def api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{BACKEND}{path}", timeout=10, **kwargs)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ─── Auto-Refresh ─────────────────────────────────────────────────────────────
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
if auto_refresh:
    import time
    time.sleep(0.5)
    st.rerun()

if st.sidebar.button("Refresh Now"):
    st.rerun()

st.sidebar.divider()
st.sidebar.markdown("**Simulate Progress**")
if st.sidebar.button("Mark Random Wave Complete"):
    waves = api("get", "/migration/waves") or []
    in_progress = [w for w in waves if w["status"] != "Completed"]
    if in_progress:
        wave = in_progress[0]
        api("patch", f"/migration/waves/{wave['id']}", params={"status": "Completed"})
        st.sidebar.success(f"Marked {wave['name']} complete.")
        st.rerun()

# ─── Data Fetch ───────────────────────────────────────────────────────────────
metrics = api("get", "/dashboard/metrics") or {}
waves_breakdown = api("get", "/dashboard/waves/breakdown") or []
strategy_dist = api("get", "/dashboard/migration/strategy-distribution") or {}
apps = api("get", "/migration/apps?limit=500") or []

if not metrics:
    st.error("Backend is not available. Please start the API server.")
    st.stop()

# ─── KPI Row ──────────────────────────────────────────────────────────────────
st.subheader("Key Performance Indicators")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Apps", metrics.get("total_apps", 0))
k2.metric(
    "Migrated",
    metrics.get("apps_migrated", 0),
    f"{metrics.get('migration_percent', 0):.1f}%",
)
k3.metric("In Progress", metrics.get("apps_in_progress", 0))
k4.metric("Pending", metrics.get("apps_pending", 0))
k5.metric("Waves Complete", f"{metrics.get('waves_completed', 0)}/{metrics.get('total_waves', 0)}")
k6.metric("Compliance", f"{metrics.get('compliance_coverage_percent', 0):.0f}%")

st.divider()

k7, k8, k9 = st.columns(3)
k7.metric("Est. Monthly Cost", f"${metrics.get('total_estimated_cost_usd', 0):,.0f}")
k8.metric("Est. Annual Savings", f"${metrics.get('total_estimated_savings_usd', 0):,.0f}")
k9.metric("Avg Risk Score", f"{metrics.get('avg_risk_score', 0):.2f} / 10")

st.divider()

# ─── Chart Row 1 ──────────────────────────────────────────────────────────────
col_prog, col_strat = st.columns(2)

with col_prog:
    st.subheader("Migration Progress")
    migrated = metrics.get("apps_migrated", 0)
    in_prog = metrics.get("apps_in_progress", 0)
    pending = metrics.get("apps_pending", 0)
    total = metrics.get("total_apps", 0) or 1

    fig_prog = go.Figure(
        go.Bar(
            x=["Migrated", "In Progress", "Pending"],
            y=[migrated, in_prog, pending],
            marker_color=["#10b981", "#f59e0b", "#6b7280"],
            text=[migrated, in_prog, pending],
            textposition="outside",
        )
    )
    fig_prog.update_layout(
        yaxis_title="Apps",
        height=300,
        showlegend=False,
        margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig_prog, use_container_width=True)

    # Progress gauge
    pct = metrics.get("migration_percent", 0)
    fig_gauge = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=pct,
            delta={"reference": 50, "valueformat": ".1f"},
            title={"text": "Migration Complete (%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2563eb"},
                "steps": [
                    {"range": [0, 30], "color": "#fee2e2"},
                    {"range": [30, 70], "color": "#fef3c7"},
                    {"range": [70, 100], "color": "#d1fae5"},
                ],
                "threshold": {"line": {"color": "green", "width": 4}, "thickness": 0.75, "value": 80},
            },
            number={"suffix": "%"},
        )
    )
    fig_gauge.update_layout(height=250, margin=dict(t=10, b=10))
    st.plotly_chart(fig_gauge, use_container_width=True)


with col_strat:
    st.subheader("Migration Strategy Distribution")
    if strategy_dist:
        labels = list(strategy_dist.keys())
        values = list(strategy_dist.values())
        fig_strat = px.pie(
            names=labels,
            values=values,
            color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b", "#6b7280"],
            hole=0.45,
        )
        fig_strat.update_layout(height=300, margin=dict(t=20, b=20))
        st.plotly_chart(fig_strat, use_container_width=True)
    else:
        st.info("Classify apps to see strategy distribution.")

    st.subheader("Compliance Posture")
    itar = metrics.get("itar_apps", 0)
    pci = metrics.get("pci_apps", 0)
    hipaa = metrics.get("hipaa_apps", 0)
    neither = (metrics.get("total_apps", 0)) - max(itar, pci, hipaa)
    fig_comp = go.Figure(
        go.Bar(
            x=["ITAR", "PCI DSS", "HIPAA", "No Framework"],
            y=[itar, pci, hipaa, neither],
            marker_color=["#dc2626", "#d97706", "#2563eb", "#9ca3af"],
            text=[itar, pci, hipaa, neither],
            textposition="outside",
        )
    )
    fig_comp.update_layout(yaxis_title="Apps", height=250, showlegend=False, margin=dict(t=5, b=5))
    st.plotly_chart(fig_comp, use_container_width=True)

# ─── Wave Timeline & Risk Heatmap ─────────────────────────────────────────────
st.divider()
col_waves, col_risk = st.columns(2)

with col_waves:
    st.subheader("Wave Progress")
    if waves_breakdown:
        df_waves = pd.DataFrame(waves_breakdown)
        fig_waves = px.bar(
            df_waves,
            x="wave_name",
            y="app_count",
            color="status",
            title="Apps per Wave",
            labels={"wave_name": "Wave", "app_count": "Apps", "status": "Status"},
            color_discrete_map={
                "Planned": "#6b7280",
                "In-Progress": "#f59e0b",
                "Completed": "#10b981",
            },
            text="app_count",
        )
        fig_waves.update_layout(height=320, margin=dict(t=30, b=30))
        st.plotly_chart(fig_waves, use_container_width=True)
    else:
        st.info("Generate a migration plan to see wave breakdown.")

with col_risk:
    st.subheader("Risk Heatmap by Wave")
    if waves_breakdown:
        df_risk = pd.DataFrame(waves_breakdown)
        fig_heat = px.bar(
            df_risk,
            x="wave_name",
            y="risk_score",
            color="risk_score",
            title="Wave Risk Scores",
            labels={"wave_name": "Wave", "risk_score": "Avg Risk"},
            color_continuous_scale="RdYlGn_r",
            text=df_risk["risk_score"].round(2),
        )
        fig_heat.update_layout(height=320, margin=dict(t=30, b=30))
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("Generate a migration plan to see risk heatmap.")

# ─── App Risk Table ───────────────────────────────────────────────────────────
st.divider()
st.subheader("Application Risk Register")
if apps:
    df_apps = pd.DataFrame(apps)
    risk_cols = [
        "name", "tech_stack", "data_sensitivity", "migration_strategy",
        "risk_score", "estimated_cost_usd", "is_itar", "is_pci", "is_hipaa", "status",
    ]
    df_risk_table = df_apps[[c for c in risk_cols if c in df_apps.columns]].copy()
    df_risk_table.rename(
        columns={
            "tech_stack": "Stack",
            "data_sensitivity": "Sensitivity",
            "migration_strategy": "Strategy",
            "risk_score": "Risk",
            "estimated_cost_usd": "Cost/mo ($)",
            "is_itar": "ITAR",
            "is_pci": "PCI",
            "is_hipaa": "HIPAA",
        },
        inplace=True,
    )
    if "Risk" in df_risk_table.columns:
        df_risk_table = df_risk_table.sort_values("Risk", ascending=False)

    st.dataframe(
        df_risk_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=10, format="%.2f"),
            "Cost/mo ($)": st.column_config.NumberColumn("Cost/mo ($)", format="$%.0f"),
            "ITAR": st.column_config.CheckboxColumn("ITAR"),
            "PCI": st.column_config.CheckboxColumn("PCI"),
            "HIPAA": st.column_config.CheckboxColumn("HIPAA"),
        },
    )

# ─── Export ───────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Export")
col_exp1, col_exp2 = st.columns(2)

with col_exp1:
    if apps and st.button("Export App Inventory (CSV)"):
        df_export = pd.DataFrame(apps)
        csv = df_export.to_csv(index=False)
        st.download_button(
            "Download CSV",
            data=csv,
            file_name=f"app_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

with col_exp2:
    if st.button("Generate Summary Report (TXT)"):
        lines = [
            "CLOUD MIGRATION COMMAND CENTER – EXECUTIVE SUMMARY",
            f"Generated: {datetime.utcnow().isoformat()}",
            "=" * 60,
            f"Total Applications:    {metrics.get('total_apps', 0)}",
            f"Migrated:              {metrics.get('apps_migrated', 0)} ({metrics.get('migration_percent', 0):.1f}%)",
            f"In Progress:           {metrics.get('apps_in_progress', 0)}",
            f"Pending:               {metrics.get('apps_pending', 0)}",
            "",
            f"Total Waves:           {metrics.get('total_waves', 0)}",
            f"Waves Completed:       {metrics.get('waves_completed', 0)}",
            "",
            f"Est. Monthly Cost:     ${metrics.get('total_estimated_cost_usd', 0):,.2f}",
            f"Est. Annual Savings:   ${metrics.get('total_estimated_savings_usd', 0):,.2f}",
            f"Average Risk Score:    {metrics.get('avg_risk_score', 0):.2f}/10",
            "",
            "COMPLIANCE",
            f"ITAR Applications:     {metrics.get('itar_apps', 0)}",
            f"PCI Applications:      {metrics.get('pci_apps', 0)}",
            f"HIPAA Applications:    {metrics.get('hipaa_apps', 0)}",
            f"Avg Compliance Score:  {metrics.get('compliance_coverage_percent', 0):.1f}%",
            "",
            "WAVE STATUS",
        ]
        for w in waves_breakdown:
            lines.append(
                f"  {w['wave_name']}: {w['app_count']} apps | "
                f"Risk: {w['risk_score']} | Status: {w['status']} | "
                f"{w.get('start_date', '?')} – {w.get('end_date', '?')}"
            )
        st.download_button(
            "Download Summary",
            data="\n".join(lines),
            file_name=f"exec_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
        )

st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
