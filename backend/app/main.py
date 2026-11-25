"""FastAPI entrypoint for KPI Reconciliation & Business Hypothesis Workbench."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .hypothesis_engine import generate_business_hypotheses
from .memo_renderer import render_insight_memo_markdown
from .reconciler import compute_independent_kpis, infer_dataset_roles, load_csv_or_excel, reconcile_snapshot

APP_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = APP_ROOT / "sample_data"

SAMPLE_CASES: Dict[str, Dict[str, Any]] = {
    "nusamart_s9_s10": {
        "id": "nusamart_s9_s10",
        "label": "NusaMart S9/S10 (Orders + Separate Reviews + Dashboard Snapshot)",
        "description": "320 orders + 500 unjoined customer reviews + 5 official S9 dashboard assertions.",
        "quant_file": "nusamart_analysis_ready.csv",
        "sentiment_file": "nusamart_reviews_labeled_s8.csv",
        "snapshot_file": "nusamart_dashboard_metrics.csv",
    },
    "swiftbite_capstone": {
        "id": "swiftbite_capstone",
        "label": "SwiftBite Capstone (320 Orders + Delivery SLA + Reviews)",
        "description": "Food delivery dataset across 5 city zones & 5 cuisines with delivery delay & sentiment.",
        "quant_file": "swiftbite_analysis_ready.csv",
        "sentiment_file": None,
        "snapshot_file": None,
        "default_snapshot": [
            {"metric": "Total Orders", "dashboard_value": 320},
            {"metric": "Net Payment Value", "dashboard_value": 38000000},
            {"metric": "Late Delivery Rate (%)", "dashboard_value": 28.47},
        ],
    },
}

app = FastAPI(
    title="KPI Reconciliation & Business Hypothesis Workbench API",
    version="1.1.0",
    description="Domain-agnostic DuckDB KPI assertions + evidence-backed candidate business hypothesis generator.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MemoRequest(BaseModel):
    dataset_name: str = "Dataset"
    analyst_name: str = "Data Analyst"
    reconciliation: Dict[str, Any] = {}
    hypotheses: List[Dict[str, Any]] = []
    analyst_decision_summary: str = ""
    recommended_actions: List[str] = []
    lang: str = "en"


def _load_sample_bundle(case_id: str):
    if case_id not in SAMPLE_CASES:
        raise HTTPException(status_code=404, detail=f"Unknown sample case '{case_id}'.")
    cfg = SAMPLE_CASES[case_id]
    q_path = SAMPLE_DIR / cfg["quant_file"]
    if not q_path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample file missing: {cfg['quant_file']}")
    quant_df = load_csv_or_excel(q_path.read_bytes(), q_path.name)

    sentiment_df = None
    if cfg.get("sentiment_file"):
        s_path = SAMPLE_DIR / cfg["sentiment_file"]
        if s_path.is_file():
            sentiment_df = load_csv_or_excel(s_path.read_bytes(), s_path.name)

    snapshot_items: List[Dict[str, Any]] = []
    if cfg.get("snapshot_file"):
        snap_path = SAMPLE_DIR / cfg["snapshot_file"]
        if snap_path.is_file():
            snap_df = load_csv_or_excel(snap_path.read_bytes(), snap_path.name)
            snapshot_items = snap_df.to_dict(orient="records")
    elif cfg.get("default_snapshot"):
        snapshot_items = cfg["default_snapshot"]

    return cfg, quant_df, sentiment_df, snapshot_items


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "engine": "duckdb+pandas"}


@app.get("/api/samples")
def list_samples() -> Dict[str, List[Dict[str, str]]]:
    items = []
    for cfg in SAMPLE_CASES.values():
        if (SAMPLE_DIR / cfg["quant_file"]).is_file():
            items.append({
                "id": cfg["id"],
                "label": cfg["label"],
                "description": cfg["description"],
            })
    return {"samples": items}


@app.post("/api/analyze/sample/{case_id}")
def analyze_sample(
    case_id: str,
    target_metric: Optional[str] = None,
    flag_col: Optional[str] = None,
    slice_col: Optional[str] = None,
    slice_val: Optional[str] = None,
    lang: str = "en",
):
    cfg, quant_df, sentiment_df, snapshot_items = _load_sample_bundle(case_id)
    roles = infer_dataset_roles(quant_df, sentiment_df)
    indep = compute_independent_kpis(
        quant_df,
        sentiment_df=sentiment_df,
        roles=roles,
        target_metric=target_metric,
        flag_col=flag_col,
        slice_col=slice_col,
        slice_val=slice_val,
    )
    reconciliation = reconcile_snapshot(
        indep["all_reconcilable_kpis"], snapshot_items, quant_df=quant_df, roles=roles, lang=lang
    )
    hyp = generate_business_hypotheses(
        quant_df,
        sentiment_df=sentiment_df,
        target_metric=target_metric,
        flag_col=flag_col,
        roles=roles,
        lang=lang,
    )
    return {
        "dataset_name": cfg["label"],
        "roles": roles,
        "independent": indep,
        "reconciliation": reconciliation,
        "hypothesis_report": hyp,
        "snapshot_items": snapshot_items,
    }


@app.post("/api/analyze/upload")
async def analyze_upload(
    quant_file: UploadFile = File(...),
    sentiment_file: Optional[UploadFile] = File(None),
    snapshot_file: Optional[UploadFile] = File(None),
    snapshot_json: Optional[str] = Form(None),
    target_metric: Optional[str] = Form(None),
    flag_col: Optional[str] = Form(None),
    slice_col: Optional[str] = Form(None),
    slice_val: Optional[str] = Form(None),
    lang: str = Form("en"),
):
    if not quant_file.filename:
        raise HTTPException(status_code=400, detail="Missing quantitative file.")
    q_bytes = await quant_file.read()
    if not q_bytes:
        raise HTTPException(status_code=400, detail="Quantitative file is empty.")
    try:
        quant_df = load_csv_or_excel(q_bytes, quant_file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sentiment_df = None
    if sentiment_file is not None and sentiment_file.filename:
        s_bytes = await sentiment_file.read()
        if s_bytes:
            sentiment_df = load_csv_or_excel(s_bytes, sentiment_file.filename)

    snapshot_items: List[Dict[str, Any]] = []
    if snapshot_file is not None and snapshot_file.filename:
        snap_bytes = await snapshot_file.read()
        if snap_bytes:
            snap_df = load_csv_or_excel(snap_bytes, snapshot_file.filename)
            snapshot_items = snap_df.to_dict(orient="records")
    elif snapshot_json:
        try:
            parsed = json.loads(snapshot_json)
            if isinstance(parsed, list):
                snapshot_items = parsed
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid snapshot_json payload.") from exc

    roles = infer_dataset_roles(quant_df, sentiment_df)
    indep = compute_independent_kpis(
        quant_df,
        sentiment_df=sentiment_df,
        roles=roles,
        target_metric=target_metric or None,
        flag_col=flag_col or None,
        slice_col=slice_col or None,
        slice_val=slice_val or None,
    )
    reconciliation = reconcile_snapshot(
        indep["all_reconcilable_kpis"], snapshot_items, quant_df=quant_df, roles=roles, lang=lang
    )
    hyp = generate_business_hypotheses(
        quant_df,
        sentiment_df=sentiment_df,
        target_metric=target_metric or None,
        flag_col=flag_col or None,
        roles=roles,
        lang=lang,
    )
    return {
        "dataset_name": quant_file.filename,
        "roles": roles,
        "independent": indep,
        "reconciliation": reconciliation,
        "hypothesis_report": hyp,
        "snapshot_items": snapshot_items,
    }


@app.post("/api/reconcile")
async def reconcile_custom_snapshot(
    sample_id: Optional[str] = Form(None),
    quant_file: Optional[UploadFile] = File(None),
    sentiment_file: Optional[UploadFile] = File(None),
    snapshot_json: str = Form("[]"),
    target_metric: Optional[str] = Form(None),
    flag_col: Optional[str] = Form(None),
    slice_col: Optional[str] = Form(None),
    slice_val: Optional[str] = Form(None),
    lang: str = Form("en"),
):
    """Re-run Gate 1 assertions when analyst edits dashboard snapshot values or tests a slice."""
    try:
        snapshot_items = json.loads(snapshot_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid snapshot_json.") from exc

    if quant_file is not None and quant_file.filename:
        quant_df = load_csv_or_excel(await quant_file.read(), quant_file.filename)
        sentiment_df = (
            load_csv_or_excel(await sentiment_file.read(), sentiment_file.filename)
            if (sentiment_file is not None and sentiment_file.filename)
            else None
        )
    elif sample_id:
        _, quant_df, sentiment_df, _ = _load_sample_bundle(sample_id)
    else:
        raise HTTPException(status_code=400, detail="Provide either sample_id or quant_file.")

    roles = infer_dataset_roles(quant_df, sentiment_df)
    indep = compute_independent_kpis(
        quant_df,
        sentiment_df=sentiment_df,
        roles=roles,
        target_metric=target_metric or None,
        flag_col=flag_col or None,
        slice_col=slice_col or None,
        slice_val=slice_val or None,
    )
    reconciliation = reconcile_snapshot(
        indep["all_reconcilable_kpis"], snapshot_items, quant_df=quant_df, roles=roles, lang=lang
    )
    return {"independent": indep, "reconciliation": reconciliation}


@app.post("/api/memo/export", response_class=PlainTextResponse)
def export_memo(req: MemoRequest):
    return render_insight_memo_markdown(req.model_dump())
