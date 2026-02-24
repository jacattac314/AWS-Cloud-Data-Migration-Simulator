"""Knowledge-Led Operations (KLO) page – document ingestion and AI-powered search."""

import os
import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Knowledge Base (KLO)", page_icon="🧠", layout="wide")
st.title("🧠 Knowledge-Led Operations (KLO)")
st.caption(
    "Upload operational docs, runbooks, and SOPs. Query the knowledge base with natural language "
    "using semantic search powered by OpenAI embeddings (TF-IDF fallback when no API key is set)."
)


def api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{BACKEND}{path}", timeout=30, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is the API server running?")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:300]}")
        return None


# ─── Sidebar – Upload Controls ────────────────────────────────────────────────
with st.sidebar:
    st.header("Ingest Documents")

    doc_title = st.text_input("Document Title *", placeholder="e.g. EC2 Migration Runbook")
    entry_type = st.selectbox("Entry Type", ["Runbook", "FAQ", "Incident", "General"])

    st.subheader("Upload Text File")
    txt_file = st.file_uploader("Plain-text (.txt)", type=["txt"], key="txt_upload")
    if txt_file and st.button("Ingest Text File", type="primary"):
        if not doc_title.strip():
            st.warning("Please enter a document title.")
        else:
            with st.spinner("Chunking and embedding..."):
                result = api(
                    "post",
                    f"/knowledge/upload/text?title={doc_title}&entry_type={entry_type}",
                    files={"file": (txt_file.name, txt_file.read(), "text/plain")},
                )
            if result is not None:
                st.success(f"Ingested {len(result)} chunks from '{txt_file.name}'.")
                st.rerun()

    st.subheader("Upload PDF")
    pdf_file = st.file_uploader("PDF document", type=["pdf"], key="pdf_upload")
    if pdf_file and st.button("Ingest PDF", type="primary"):
        if not doc_title.strip():
            st.warning("Please enter a document title.")
        else:
            with st.spinner("Extracting text and embedding..."):
                result = api(
                    "post",
                    f"/knowledge/upload/pdf?title={doc_title}&entry_type={entry_type}",
                    files={"file": (pdf_file.name, pdf_file.read(), "application/pdf")},
                )
            if result is not None:
                st.success(f"Ingested {len(result)} chunks from '{pdf_file.name}'.")
                st.rerun()

    st.divider()
    st.subheader("Sample Data")
    if st.button("Load Demo Runbook"):
        demo_text = """# EC2 Instance Migration Runbook

## Overview
This runbook describes the procedure for migrating an EC2 instance from one AWS region
to another using AMI snapshots and Launch Templates.

## Prerequisites
- AWS CLI v2 configured with appropriate IAM permissions
- Source instance must be stopped or have an AMI snapshot ready
- Target VPC and security groups configured in destination region
- KMS key available in target region for EBS encryption

## Migration Steps

### Step 1: Create AMI from Source Instance
1. Navigate to EC2 console in source region.
2. Select the target instance and choose Actions > Image and templates > Create image.
3. Enter image name (e.g., myapp-migration-2026-02-24) and description.
4. Check "No reboot" only if the application supports online snapshot.
5. Note the AMI ID (ami-xxxxxxxxxxxxxxxxx) once creation completes.

### Step 2: Copy AMI to Target Region
```bash
aws ec2 copy-image \\
  --source-image-id ami-xxxxxxxxxxxxxxxxx \\
  --source-region us-east-1 \\
  --region us-west-2 \\
  --name "myapp-migration-copy" \\
  --encrypted \\
  --kms-key-id arn:aws:kms:us-west-2:123456789:key/mrk-abc123
```

### Step 3: Launch Instance in Target Region
1. Wait for AMI copy to complete (Status: available).
2. Use Launch Instance wizard or Launch Template.
3. Select the copied AMI as the base.
4. Configure instance type, VPC, subnet, security groups.
5. Add EBS volumes with encryption using regional KMS key.

### Step 4: Validate Application Health
1. SSH into new instance: `ssh -i keypair.pem ec2-user@<new-ip>`
2. Check application service status: `systemctl status myapp`
3. Run smoke tests against the new IP/hostname.
4. Update DNS or load balancer target groups.

### Step 5: Cutover
1. Update Route 53 record or ALB target group to point to new instance.
2. Monitor CloudWatch metrics for 15 minutes post-cutover.
3. Terminate old instance after 24 hours of stable operation.

## Rollback Procedure
1. Revert DNS/load balancer to original instance.
2. Restart original instance if stopped.
3. Investigate failure and re-attempt migration after root cause fix.

## Verification Checklist
- [ ] Application endpoints responding (HTTP 200)
- [ ] Database connections established
- [ ] Logs flowing to CloudWatch
- [ ] CloudTrail events recorded
- [ ] IAM roles attached correctly
- [ ] Security groups allow required ports only

## Troubleshooting
- **Boot failure after AMI copy**: Check EBS encryption key permissions in target region.
- **Missing data volumes**: Ensure all attached volumes were included in AMI snapshot.
- **IAM permission errors**: Verify instance profile role is recreated in target region.
- **Network connectivity issues**: Check VPC peering or VPN configuration.

## Compliance Notes
For ITAR-classified workloads, use AWS GovCloud (US) regions only:
- us-gov-west-1 (Oregon)
- us-gov-east-1 (Virginia)
KMS keys must be in the same GovCloud region as the instance.
"""
        result = api(
            "post",
            "/knowledge/upload/text?title=EC2%20Instance%20Migration%20Runbook&entry_type=Runbook",
            files={"file": ("demo_runbook.txt", demo_text.encode(), "text/plain")},
        )
        if result is not None:
            st.success(f"Loaded demo runbook ({len(result)} chunks).")
            st.rerun()

    st.divider()
    if st.button("Clear All Entries", type="secondary"):
        with st.spinner("Clearing..."):
            requests.delete(f"{BACKEND}/knowledge/entries", timeout=10)
        st.success("Knowledge base cleared.")
        st.rerun()


# ─── Main Tabs ────────────────────────────────────────────────────────────────
tab_search, tab_browse, tab_runbook = st.tabs(["AI Search / Chat", "Browse Entries", "Generate Runbook"])

# ─── Tab 1: AI Search ─────────────────────────────────────────────────────────
with tab_search:
    st.subheader("Ask the Knowledge Base")

    if "klo_history" not in st.session_state:
        st.session_state["klo_history"] = []

    query = st.text_input(
        "Your question",
        placeholder="e.g. How do I migrate an EC2 instance to us-gov-west-1?",
        key="klo_query",
    )
    col_k, col_btn = st.columns([1, 5])
    top_k = col_k.number_input("Top K results", min_value=1, max_value=10, value=3)

    if st.button("Search", type="primary") and query.strip():
        with st.spinner("Searching knowledge base..."):
            result = api(
                "post",
                "/knowledge/search",
                json={"query": query, "top_k": top_k},
            )
        if result:
            st.session_state["klo_history"].append(
                {"query": query, "answer": result.get("answer"), "results": result.get("results", [])}
            )

    # Chat History
    for item in reversed(st.session_state["klo_history"]):
        with st.container(border=True):
            st.markdown(f"**You:** {item['query']}")
            if item.get("answer"):
                st.markdown(f"**AI Answer:** {item['answer']}")
            st.divider()
            if item.get("results"):
                with st.expander(f"Source chunks ({len(item['results'])} found)"):
                    for r in item["results"]:
                        score_pct = int(r["score"] * 100)
                        st.markdown(
                            f"**{r['entry']['title']}** — Relevance: `{score_pct}%`\n\n"
                            f"> {r['excerpt']}"
                        )
                        st.divider()

    if st.session_state["klo_history"] and st.button("Clear Chat History"):
        st.session_state["klo_history"] = []
        st.rerun()


# ─── Tab 2: Browse ─────────────────────────────────────────────────────────────
with tab_browse:
    st.subheader("Knowledge Base Entries")
    entries = api("get", "/knowledge/entries?limit=200") or []

    if not entries:
        st.info("No entries yet – upload a document or load the demo runbook.")
    else:
        # Group by source file
        sources = {}
        for e in entries:
            src = e.get("source_file") or "Manual Entry"
            sources.setdefault(src, []).append(e)

        st.markdown(f"**{len(entries)} total chunks** across {len(sources)} source(s).")

        for src, chunks in sources.items():
            with st.expander(f"📄 {src} ({len(chunks)} chunks)"):
                for chunk in chunks:
                    st.markdown(
                        f"**Chunk {chunk['chunk_index'] + 1}** · `{chunk['entry_type']}`  \n"
                        f"{chunk['content'][:200]}{'...' if len(chunk['content']) > 200 else ''}"
                    )
                    st.divider()


# ─── Tab 3: Generate Runbook ──────────────────────────────────────────────────
with tab_runbook:
    st.subheader("Auto-Generate Runbook")
    st.caption(
        "Enter a topic and the system will retrieve relevant knowledge and use AI "
        "(OpenAI GPT-4o, or a simple template if no API key) to draft a structured runbook."
    )

    topic = st.text_input("Runbook Topic", placeholder="e.g. Rollback procedure for EC2 migration failure")
    if st.button("Generate Runbook", type="primary") and topic.strip():
        with st.spinner("Generating runbook from knowledge base..."):
            result = api("post", f"/knowledge/generate/runbook?topic={topic}&top_k=5")
        if result:
            st.markdown("---")
            st.markdown(result["runbook"])
            st.download_button(
                "Download Runbook (Markdown)",
                data=result["runbook"],
                file_name=f"runbook_{topic[:30].replace(' ', '_')}.md",
                mime="text/markdown",
            )
