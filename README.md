# Cloud Migration Command Center

> Enterprise-grade AWS migration planning, KLO knowledge search, ITAR/PCI/HIPAA compliance,
> and executive dashboard – built as a portfolio demo of large-scale cloud migration governance.

---

## Overview

The **Cloud Migration Command Center (CMCC)** is a full-stack application that simulates an
end-to-end AWS-to-data-center migration program with enterprise governance. It demonstrates:

- **Migration Planning** – auto-classify apps (Rehost/Replatform/Refactor), dependency-aware
  wave grouping, risk scoring, and cost estimation.
- **Knowledge-Led Operations (KLO)** – semantic search over operational runbooks using OpenAI
  embeddings (TF-IDF fallback when no API key is configured).
- **Compliance Module** – ITAR/PCI DSS/HIPAA control checklists with AWS GovCloud simulation
  and compliance scoring.
- **Executive Dashboard** – real-time KPI charts (migration progress, cost savings, risk
  heatmap, compliance posture).

---

## Quick Start

### Prerequisites

- Python 3.12+
- (Optional) OpenAI API key for AI-powered KLO features

### 1. Clone & Install

```bash
git clone <repo-url>
cd AWS-Cloud-Data-Migration-Simulator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env – set OPENAI_API_KEY if you want AI-powered KLO
```

### 3. Start the Backend API

```bash
uvicorn backend.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 4. Start the Streamlit Frontend

```bash
streamlit run frontend/Home.py
```

Open: http://localhost:8501

---

## Docker Compose (Recommended)

```bash
cp .env.example .env   # add OPENAI_API_KEY if desired
docker-compose up --build
```

| Service   | URL                          |
|-----------|------------------------------|
| Frontend  | http://localhost:8501        |
| Backend   | http://localhost:8000        |
| API Docs  | http://localhost:8000/docs   |

---

## Running Tests

```bash
pytest --tb=short -q
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Cloud Migration Command Center                  │
│                                                              │
│  ┌──────────────┐    REST    ┌──────────────────────────┐   │
│  │  Streamlit   │◄──────────►│  FastAPI Backend          │   │
│  │  Frontend    │            │  (Python 3.12)            │   │
│  │  4 modules   │            ├──────────────────────────┤   │
│  └──────────────┘            │  migration_service.py     │   │
│                              │  klo_service.py           │   │
│  ┌──────────────┐            │  compliance_service.py    │   │
│  │  OpenAI API  │◄───────────│  dashboard router         │   │
│  │  Embeddings  │            └────────────┬─────────────┘   │
│  │  + Chat      │                         │                  │
│  └──────────────┘            ┌────────────▼─────────────┐   │
│                              │  SQLite / PostgreSQL       │   │
│  ┌──────────────┐            │  Apps, Waves, Plans       │   │
│  │  Terraform   │            │  KnowledgeEntries          │   │
│  │  Templates   │            │  ComplianceControls        │   │
│  └──────────────┘            │  AuditLog                  │   │
│                              └──────────────────────────-─┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
.
├── frontend/
│   ├── Home.py                         # Streamlit landing page
│   └── pages/
│       ├── 1_Migration_Planner.py      # Upload, classify, plan waves
│       ├── 2_Knowledge_Base.py         # KLO search & runbook generation
│       ├── 3_Compliance_Center.py      # ITAR/PCI/HIPAA controls
│       └── 4_Executive_Dashboard.py    # KPI charts & export
├── backend/
│   ├── main.py                         # FastAPI app + CORS
│   ├── config.py                       # Pydantic settings
│   ├── models/
│   │   ├── database.py                 # SQLAlchemy ORM models
│   │   └── schemas.py                  # Pydantic request/response schemas
│   ├── routers/
│   │   ├── migration.py                # /migration/* endpoints
│   │   ├── knowledge.py                # /knowledge/* endpoints
│   │   ├── compliance.py               # /compliance/* endpoints
│   │   └── dashboard.py                # /dashboard/* endpoints
│   └── services/
│       ├── migration_service.py        # Wave grouping, classification, CSV import
│       ├── klo_service.py              # Chunking, embedding, semantic search
│       └── compliance_service.py       # Control definitions, sync, scoring
├── tests/
│   ├── test_migration.py               # Migration service unit tests
│   ├── test_compliance.py              # Compliance service unit tests
│   ├── test_klo.py                     # KLO service unit tests
│   └── test_api.py                     # FastAPI integration tests
├── knowledge/
│   └── sample_runbook.txt              # Demo operational runbooks + FAQs
├── infra/
│   └── main.tf                         # Terraform: VPC, RDS, ECS, KMS, CloudTrail
├── .github/workflows/ci.yml            # GitHub Actions CI
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Key Features

### Migration Planner
- **Auto-classification** using AWS 7-Rs heuristics (keyword matching on tech stack)
- **Topological wave grouping** via Kahn's algorithm for dependency-aware ordering
- **Risk scoring** based on data sensitivity, SLA tier, compliance flags, and strategy
- **Cost estimation** rule-based TCO model (monthly AWS cost vs. on-prem savings)
- **CSV bulk import** with validation and duplicate detection

### KLO Engine
- **Document ingestion** – text/PDF upload → chunking → embedding → storage
- **Dual embedding backend** – OpenAI `text-embedding-3-small` when API key present,
  TF-IDF cosine similarity otherwise (zero external dependencies)
- **AI-synthesized answers** via GPT-4o (or rule-based excerpt fallback)
- **Runbook generation** from retrieved knowledge context

### Compliance Module
- **Framework coverage**: ITAR (7 controls), PCI DSS (6 controls), HIPAA (6 controls)
- Controls reference actual AWS GovCloud FAQ and AWS compliance guides
- **Compliance score** (0–100%) per app with drill-down
- **CloudTrail-style audit log** of all compliance actions

### Executive Dashboard
- Gauge chart for overall migration %, bar charts for wave progress
- Risk heatmap by wave, strategy distribution pie chart
- Compliance posture breakdown (ITAR / PCI / HIPAA apps)
- CSV and TXT export

---

## Compliance Reference

| Framework | Key AWS Control | Source |
|-----------|----------------|--------|
| ITAR | Deploy in AWS GovCloud (US) | AWS GovCloud FAQ |
| ITAR | Encryption at rest (KMS) | AWS ITAR Compliance Guide |
| ITAR | CloudTrail + S3 Object Lock | AWS GovCloud FAQ |
| PCI DSS | AES-256 storage + TLS 1.2+ | PCI DSS v4.0 |
| PCI DSS | CDE network segmentation | PCI DSS Req 1 |
| HIPAA | BAA with AWS | HIPAA § 164.308 |
| HIPAA | FIPS 140-2 encryption | HIPAA § 164.312 |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./migration_cmd_center.db` | SQLAlchemy DB URL |
| `OPENAI_API_KEY` | *(empty)* | OpenAI key – enables AI embeddings & chat |
| `BACKEND_URL` | `http://localhost:8000` | Backend URL used by Streamlit |
| `APP_ENV` | `development` | Environment name |
| `SECRET_KEY` | dev default | JWT/session secret – change in production |

---

## License

This project is a portfolio demonstration. All code is original.
