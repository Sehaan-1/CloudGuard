---
title: CloudGuard FinOps Platform
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8050
pinned: false
license: mit
---

# CloudGuard

**Intelligent Cloud Cost Optimizer & FinOps Observability Platform**

[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-217%20passed-success?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)](https://github.com/Sehaan-1/CloudGuard)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple)](LICENSE)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Sehaan-1/CloudGuard)

CloudGuard is an enterprise-grade FinOps platform that unifies multi-cloud infrastructure analytics (AWS, Azure, Mock), audits cloud waste (idle compute, orphaned storage, untagged assets), detects spending anomalies via statistical machine learning heuristics, and delivers actionable rightsizing recommendations with projected ROI.

---

## Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Multi-Cloud Ingestion Layer"]
        AWS["AWS Provider (EC2, S3, CloudWatch, Cost Explorer)"]
        AZ["Azure Provider (Compute, Storage, Monitor, Cost Mgmt)"]
        MOCK["Mock Provider (Synthetic High-Fidelity Multi-Cloud)"]
    end

    subgraph Processing["2. Parallel Analytics & Intelligence Engine"]
        PP["Parallel Processor (Chunked Streaming & Multiprocessing)"]
        AD["Anomaly Detection Ensemble (Z-Score, IQR, Rolling Window, Composite)"]
        RE["Recommendation Engine (Waste Audit, Rightsizing, ROI Estimator)"]
    end

    subgraph DataLayer["3. Persistence & Distributed Cache"]
        DB["Async SQLAlchemy 2.0 (PostgreSQL / SQLite via aiosqlite)"]
        CACHE["Cache Layer (Redis with In-Memory Fallback)"]
    end

    subgraph Delivery["4. FinOps Delivery Interfaces"]
        DASH["Observability Web Dashboard (Plotly Dash & FastAPI)"]
        CLI["Typer CLI (Analyze, Scan, Report, Dashboard)"]
        API["REST API (/api/v1/health, costs, anomalies, scan)"]
        REP["Executive Report Generator (Jinja2 & WeasyPrint PDF/HTML)"]
    end

    Ingestion --> PP
    PP --> AD
    PP --> RE
    AD --> DataLayer
    RE --> DataLayer
    DataLayer --> Delivery
```

---

## Key Features

- **Multi-Cloud Ingestion Strategy**: Unified data model across AWS, Azure, and zero-config deterministic Mock providers.
- **Sub-5s Analytics Performance**: Parallel multiprocessing processor capable of crunching **100,000+ line-item records in under 5 seconds**.
- **Statistical Anomaly Detection**: Ensemble voting combining Z-Score, Interquartile Range (IQR), and Rolling-Window volatility models.
- **Automated Cloud Waste Audit**: Instant detection of idle compute (<5% CPU), unattached / orphaned disks, underutilized VMs, and untagged infrastructure.
- **Actionable Optimization Recommendations**: Priority-ranked recommendations with instant and annual cost savings projections.
- **Interactive FinOps Dashboard**: Dual FastAPI + Plotly Dash interface with real-time KPI cards, cost trend explorer, and anomaly timelines.
- **Executive PDF & HTML Reports**: Publication-ready downloadable reports for C-suite and FinOps stakeholders.
- **Enterprise-Ready DevOps**: Multi-stage Docker container, Docker Compose (App + PostgreSQL + Redis), and 217 automated CI tests.

---

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Sehaan-1/CloudGuard.git
cd CloudGuard

# Install in editable mode with development & reporting dependencies
pip install -e ".[dev,postgres,pdf]"
```

### 2. Launch Observability Web Dashboard

Start the full dashboard on port `8050` with instant synthetic FinOps telemetry:

```bash
cloudguard dashboard --host 0.0.0.0 --port 8050
```

- **Dashboard UI**: `http://localhost:8050`
- **Interactive API Docs (Swagger UI)**: `http://localhost:8050/docs`

---

## CLI Commands

CloudGuard provides a Rich terminal CLI with interactive formatters:

```bash
# Analyze 30-day cost consumption and identify top spenders
cloudguard analyze --provider mock --days 30

# Scan infrastructure for idle instances and orphaned disks
cloudguard scan --provider mock --type all

# Detect spending anomalies using composite ensemble voting
cloudguard anomalies --provider mock --method composite

# Generate optimization recommendations
cloudguard recommend --provider mock

# Export executive PDF or HTML report
cloudguard report --provider mock --format pdf --output reports/finops-audit.pdf
```

---

## Docker & Docker Compose

Deploy the production stack (CloudGuard Dashboard, PostgreSQL 16, Redis 7):

```bash
# Copy and configure environment variables
cp .env.example .env

# Spin up all services
docker compose up -d

# Verify service health
curl -f http://localhost:8050/api/v1/health
```

To run standalone with embedded storage:

```bash
docker build -t cloudguard:latest .
docker run -d -p 8050:8050 cloudguard:latest
```

---

## REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Service health status and version |
| `GET` | `/api/v1/costs/summary` | Financial aggregations and service breakdown |
| `GET` | `/api/v1/resources/scan` | Audit scan results (idle, orphaned, waste metrics) |
| `GET` | `/api/v1/anomalies` | Detected cost anomalies with severity classification |
| `GET` | `/api/v1/recommendations` | FinOps rightsizing actions and estimated savings |
| `POST`| `/api/v1/reports/pdf` | Generate and stream executive PDF audit report |

---

## Testing & Verification

Run the comprehensive test suite:

```bash
# Run all 217 unit, integration, performance, and E2E CLI tests
pytest -v

# Run with coverage report (target >= 85%)
pytest --cov=cloudguard --cov-report=term-missing

# Run 100k-record high-volume processing benchmark
python scripts/benchmark.py --records 100000
```

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
