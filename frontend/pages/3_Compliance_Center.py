"""Compliance Center page – ITAR/PCI/HIPAA tagging, control checklists, audit reports."""

import os
from datetime import datetime

import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Compliance Center", page_icon="🔐", layout="wide")
st.title("🔐 Compliance Center")
st.caption(
    "Tag apps with ITAR, PCI DSS, and HIPAA classifications. "
    "Review required AWS controls, track implementation status, and generate audit reports."
)


def api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{BACKEND}{path}", timeout=15, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is the API server running?")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:300]}")
        return None


FRAMEWORK_COLORS = {
    "ITAR": "#dc2626",   # red
    "PCI":  "#d97706",   # amber
    "HIPAA": "#2563eb",  # blue
}

FRAMEWORK_ICONS = {"ITAR": "🔴", "PCI": "🟡", "HIPAA": "🔵"}


def render_compliance_badge(framework: str) -> str:
    color = FRAMEWORK_COLORS.get(framework, "#6b7280")
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:9999px;font-size:0.78rem;font-weight:600;">{framework}</span>'
    )


# ─── Sidebar – Summary ────────────────────────────────────────────────────────
with st.sidebar:
    summary = api("get", "/compliance/summary") or {}
    st.header("Portfolio Summary")
    if summary:
        st.metric("Total Apps", summary.get("total_apps", 0))
        st.metric("Avg Compliance Score", f"{summary.get('avg_compliance_score', 0)}%")
        st.metric("Fully Compliant", summary.get("fully_compliant_apps", 0))
        st.metric("Non-Compliant", summary.get("non_compliant_apps", 0))
        st.divider()
        st.markdown(f"🔴 **ITAR apps:** {summary.get('itar_apps', 0)}")
        st.markdown(f"🟡 **PCI apps:** {summary.get('pci_apps', 0)}")
        st.markdown(f"🔵 **HIPAA apps:** {summary.get('hipaa_apps', 0)}")


# ─── App Selector ─────────────────────────────────────────────────────────────
apps = api("get", "/migration/apps") or []
if not apps:
    st.warning("No apps in inventory. Go to **Migration Planner** to add apps first.")
    st.stop()

app_names = {f"{a['name']} (ID:{a['id']})": a["id"] for a in apps}
selected_label = st.selectbox("Select Application", list(app_names.keys()))
selected_app_id = app_names[selected_label]
selected_app = next((a for a in apps if a["id"] == selected_app_id), None)

if not selected_app:
    st.error("Could not load app details.")
    st.stop()

# ─── App Header ───────────────────────────────────────────────────────────────
col_hdr, col_flags = st.columns([2, 1])
with col_hdr:
    st.subheader(f"App: {selected_app['name']}")
    st.caption(
        f"Region: `{selected_app.get('region', 'N/A')}` | "
        f"Stack: `{selected_app.get('tech_stack', 'N/A')}` | "
        f"Sensitivity: `{selected_app.get('data_sensitivity', 'N/A')}`"
    )
    badges = ""
    if selected_app.get("is_itar"):
        badges += render_compliance_badge("ITAR") + " "
    if selected_app.get("is_pci"):
        badges += render_compliance_badge("PCI") + " "
    if selected_app.get("is_hipaa"):
        badges += render_compliance_badge("HIPAA") + " "
    if badges:
        st.markdown(badges, unsafe_allow_html=True)
    else:
        st.markdown("*No compliance frameworks assigned.*")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_tags, tab_controls, tab_report, tab_audit = st.tabs(
    ["Compliance Tags", "Control Checklist", "Audit Report", "Audit Log"]
)

# ─── Tab 1: Tags ──────────────────────────────────────────────────────────────
with tab_tags:
    st.subheader("Assign Compliance Frameworks")

    with st.form("tags_form"):
        st.markdown("Select all frameworks that apply to this application:")
        t1, t2, t3 = st.columns(3)

        is_itar = t1.checkbox(
            "🔴 ITAR",
            value=bool(selected_app.get("is_itar")),
            help="International Traffic in Arms Regulations – requires AWS GovCloud (US) deployment",
        )
        is_pci = t2.checkbox(
            "🟡 PCI DSS",
            value=bool(selected_app.get("is_pci")),
            help="Payment Card Industry Data Security Standard – cardholder data protection",
        )
        is_hipaa = t3.checkbox(
            "🔵 HIPAA",
            value=bool(selected_app.get("is_hipaa")),
            help="Health Insurance Portability and Accountability Act – electronic PHI protection",
        )

        if st.form_submit_button("Save Tags", type="primary"):
            result = api(
                "patch",
                f"/compliance/apps/{selected_app_id}/tags",
                params={"is_itar": is_itar, "is_pci": is_pci, "is_hipaa": is_hipaa},
            )
            if result:
                st.success("Compliance tags updated. Controls checklist refreshed.")
                st.rerun()

    # Framework information boxes
    if selected_app.get("is_itar"):
        st.info(
            "**ITAR Requirement:** This app must be deployed exclusively in **AWS GovCloud (US)** "
            "regions (us-gov-west-1 or us-gov-east-1). AWS GovCloud is physically isolated, "
            "managed by US persons only, and treats all data as ITAR-controlled by default.",
            icon="🔴",
        )

    if selected_app.get("is_pci"):
        st.warning(
            "**PCI DSS Requirement:** Cardholder data must be encrypted at rest (AES-256) and in "
            "transit (TLS 1.2+). The Cardholder Data Environment (CDE) must be network-isolated. "
            "Annual penetration testing is required.",
            icon="🟡",
        )

    if selected_app.get("is_hipaa"):
        st.info(
            "**HIPAA Requirement:** A Business Associate Agreement (BAA) must be executed with AWS. "
            "ePHI must be encrypted using FIPS 140-2 validated algorithms. Access logs must be "
            "maintained for 6 years.",
            icon="🔵",
        )


# ─── Tab 2: Controls Checklist ────────────────────────────────────────────────
with tab_controls:
    st.subheader("Controls Checklist")
    controls = api("get", f"/compliance/apps/{selected_app_id}/controls") or []

    if not controls:
        st.info("No compliance frameworks assigned. Set ITAR/PCI/HIPAA tags first.")
    else:
        # Group by framework
        by_framework: dict = {}
        for ctrl in controls:
            by_framework.setdefault(ctrl["framework"], []).append(ctrl)

        implemented_count = sum(1 for c in controls if c["is_implemented"])
        total_count = len(controls)
        pct = int(100 * implemented_count / total_count) if total_count else 0

        st.progress(pct / 100, text=f"Compliance: {implemented_count}/{total_count} controls implemented ({pct}%)")

        for fw, fw_controls in by_framework.items():
            fw_icon = FRAMEWORK_ICONS.get(fw, "⚪")
            fw_done = sum(1 for c in fw_controls if c["is_implemented"])
            st.markdown(
                f"#### {fw_icon} {fw} &nbsp;&nbsp;"
                f"<small style='color:#6b7280;'>{fw_done}/{len(fw_controls)} implemented</small>",
                unsafe_allow_html=True,
            )
            for ctrl in fw_controls:
                ctrl_key = f"ctrl_{ctrl['id']}"
                with st.expander(
                    f"{'✅' if ctrl['is_implemented'] else '⬜'} {ctrl['control_name']}",
                    expanded=not ctrl["is_implemented"],
                ):
                    st.caption(ctrl.get("description", ""))
                    col_chk, col_notes = st.columns([1, 3])
                    new_val = col_chk.checkbox(
                        "Implemented",
                        value=ctrl["is_implemented"],
                        key=f"chk_{ctrl['id']}",
                    )
                    notes_val = col_notes.text_input(
                        "Implementation Notes",
                        value=ctrl.get("notes") or "",
                        key=f"notes_{ctrl['id']}",
                        placeholder="e.g. Enabled via Terraform module v3.2",
                    )
                    if st.button("Save", key=f"save_{ctrl['id']}", type="secondary"):
                        result = api(
                            "patch",
                            f"/compliance/controls/{ctrl['id']}",
                            json={
                                "control_id": ctrl["id"],
                                "is_implemented": new_val,
                                "notes": notes_val or None,
                            },
                        )
                        if result:
                            st.success("Control updated.")
                            st.rerun()


# ─── Tab 3: Audit Report ──────────────────────────────────────────────────────
with tab_report:
    st.subheader("Compliance Audit Report")
    if st.button("Generate Report", type="primary"):
        report = api("get", f"/compliance/apps/{selected_app_id}/report")
        if report:
            st.markdown(f"## Compliance Report: {report['app_name']}")
            st.caption(f"Generated: {report.get('generated_at', datetime.utcnow().isoformat())}")

            frameworks = report.get("frameworks", [])
            if frameworks:
                st.markdown(
                    "**Frameworks:** "
                    + " ".join(render_compliance_badge(f) for f in frameworks),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("**Frameworks:** None assigned")

            score = report["compliance_score"]
            score_color = "green" if score >= 80 else "orange" if score >= 50 else "red"
            st.markdown(
                f"**Compliance Score:** "
                f"<span style='color:{score_color};font-weight:700;font-size:1.3rem;'>{score}%</span>",
                unsafe_allow_html=True,
            )

            controls_list = report.get("controls", [])
            if controls_list:
                st.divider()
                st.markdown("### Control Status")

                by_fw: dict = {}
                for c in controls_list:
                    by_fw.setdefault(c["framework"], []).append(c)

                for fw, fw_ctrls in by_fw.items():
                    st.markdown(f"**{FRAMEWORK_ICONS.get(fw, '')} {fw}**")
                    for c in fw_ctrls:
                        icon = "✅" if c["is_implemented"] else "❌"
                        note = f" — *{c['notes']}*" if c.get("notes") else ""
                        st.markdown(f"- {icon} **{c['control_name']}**{note}")
                    st.markdown("")

            # Download as text
            lines = [
                f"COMPLIANCE AUDIT REPORT",
                f"Application: {report['app_name']}",
                f"Generated: {datetime.utcnow().isoformat()}",
                f"Frameworks: {', '.join(frameworks) if frameworks else 'None'}",
                f"Compliance Score: {score}%",
                "",
                "CONTROLS:",
            ]
            for c in controls_list:
                status = "IMPLEMENTED" if c["is_implemented"] else "PENDING"
                lines.append(f"[{status}] [{c['framework']}] {c['control_name']}")
                if c.get("notes"):
                    lines.append(f"  Notes: {c['notes']}")

            st.download_button(
                "Download Report (TXT)",
                data="\n".join(lines),
                file_name=f"compliance_report_{report['app_name']}.txt",
                mime="text/plain",
            )


# ─── Tab 4: Audit Log ─────────────────────────────────────────────────────────
with tab_audit:
    st.subheader("CloudTrail-style Audit Log")
    st.caption("Immutable record of all compliance actions in the system.")
    logs = api("get", "/dashboard/audit-logs?limit=50") or []
    if not logs:
        st.info("No audit events recorded yet.")
    else:
        for log in logs:
            st.markdown(
                f"`{log['timestamp'][:19]}` &nbsp; **{log['action']}** "
                f"— {log.get('resource_type', '')} `{log.get('resource_id', '')}`"
            )
