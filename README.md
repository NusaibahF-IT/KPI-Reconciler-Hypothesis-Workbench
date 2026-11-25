# KPI Reconciler & Business Hypothesis Workbench

A reusable Data Analyst workbench combining **Gate 1: Dashboard KPI Reconciliation & Automated Assertions** with **Gate 2: Evidence-Backed Candidate Business Hypothesis Generation** and **Gate 3: Human-in-the-Loop 1-Page Insight Memo Export**.

## Core Guardrails
1. **Verify Numbers First (`MATCH / MISMATCH`):** Independently recalculates KPIs via DuckDB SQL before investigating business drivers.
2. **Hypotheses Only (No Auto-Decisions):** Outputs candidate hypotheses with 4 mandatory parts (`Observed Signal`, `Candidate Hypothesis`, `Alternative Explanations`, `Verification Checks Needed`). Final business conclusions remain with the Data Analyst.
3. **Separate Sentiment Layer:** Supports unjoined customer review datasets alongside order datasets without forcing invalid joins.
4. **Apple-to-Apple & Sample Size Checks:** Normalizes period shifts by daily run-rate and flags segments with `n < 30`.

## Running Locally

### 1. Backend (`http://127.0.0.1:8000`)
```bash
cd tools/kpi_hypothesis_workbench/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Run tests:
```bash
cd tools/kpi_hypothesis_workbench/backend
.venv/bin/pytest -v
```

### 2. Frontend (`http://127.0.0.1:3000`)
```bash
cd tools/kpi_hypothesis_workbench/frontend
npm install
npm run dev
```

## Deploying to Vercel (Single Project via Vercel Services — Beta)
Root `vercel.json` routes `/` to `frontend` (Nuxt 3) and `/api/*` to `backend` (`app.main:app`).
