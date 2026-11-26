"""Automated tests for KPI Reconciliation & Business Hypothesis Workbench."""
from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_nusamart_s9_s10_sample_reconciliation_passes():
    resp = client.post("/api/analyze/sample/nusamart_s9_s10")
    assert resp.status_code == 200
    data = resp.json()

    rec = data["reconciliation"]
    assert rec["overall_gate"] == "PASS"
    assert rec["matched"] == 5
    assert rec["mismatched"] == 0
    assert data["roles"]["sentiment_is_separate_layer"] is True

    hyp = data["hypothesis_report"]
    assert hyp["total_hypotheses"] > 0
    first = hyp["hypotheses"][0]
    for key in (
        "hypothesis_id",
        "observed_signal",
        "candidate_hypothesis",
        "alternative_explanations",
        "verification_checks_needed",
        "sample_size_flag",
    ):
        assert key in first


def test_swiftbite_capstone_fast_food_slice_and_bottleneck_hypothesis():
    resp = client.post("/api/analyze/sample/swiftbite_capstone?slice_col=cuisine_type&slice_val=Fast%20Food")
    assert resp.status_code == 200
    data = resp.json()
    kpis = data["independent"]["kpis"]
    assert kpis["Unique order_id"] == 54
    assert kpis["Sum (net_payment_amount)"] == 6078000.0
    assert kpis["Rate is_late (%)"] == 39.58

    full_resp = client.post("/api/analyze/sample/swiftbite_capstone")
    assert full_resp.status_code == 200
    full_data = full_resp.json()
    hyps = full_data["hypothesis_report"]["hypotheses"]
    assert any(h["category"] == "Outcome Rate Anomaly" and h["segment"] == "Fast Food" for h in hyps)


def test_external_saas_churn_domain_agnostic_override():
    # Simulate an external SaaS / Marketing dataset outside bootcamp e-commerce
    rows = ["account_id,created_at,plan_tier,region,ad_spend,mrr,is_churned"]
    for i in range(40):
        plan = "Starter" if i < 20 else "Enterprise"
        mrr = 50 if i < 20 else 450
        spend = 120 if i < 20 else 80
        churn = "True" if (i < 12) else "False"  # 60% churn in Starter vs 0% in Enterprise
        day = f"2026-0{(i % 2) + 1}-{(i % 20) + 1:02d}"
        rows.append(f"ACC-{i:03d},{day},{plan},APAC,{spend},{mrr},{churn}")

    csv_bytes = "\n".join(rows).encode("utf-8")
    snapshot = [
        {"metric": "Sum (ad_spend)", "dashboard_value": 4000},
        {"metric": "Rate is_churned (%)", "dashboard_value": 30.0},
    ]

    resp = client.post(
        "/api/analyze/upload",
        files={"quant_file": ("saas_accounts.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={
            "snapshot_json": json.dumps(snapshot),
            "target_metric": "ad_spend",
            "flag_col": "is_churned",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["roles"]["binary_flag_cols"] == ["is_churned"]
    assert "ad_spend" in data["roles"]["numeric_cols"]
    assert "mrr" in data["roles"]["numeric_cols"]
    assert data["reconciliation"]["overall_gate"] == "PASS"

    hyps = data["hypothesis_report"]["hypotheses"]
    assert any(h["category"] == "Outcome Rate Anomaly" and h["segment"] == "Starter" for h in hyps)
    assert data["hypothesis_report"]["target_metric"] == "ad_spend"


def test_indonesian_localization_on_hypotheses_and_memo():
    resp = client.post("/api/analyze/sample/swiftbite_capstone?lang=id")
    assert resp.status_code == 200
    data = resp.json()
    assert "Cocok dengan perhitungan independen DuckDB" in data["reconciliation"]["results"][0]["diagnosis"]
    hyps = data["hypothesis_report"]["hypotheses"]
    assert any("Kandidat hipotesa:" in h["candidate_hypothesis"] for h in hyps)

    memo_resp = client.post(
        "/api/memo/export",
        json={
            "dataset_name": "SwiftBite",
            "analyst_name": "Nusaibah",
            "reconciliation": data["reconciliation"],
            "hypotheses": hyps[:1],
            "lang": "id",
        },
    )
    assert memo_resp.status_code == 200
    assert "Memo Insight & Ringkasan Rekonsiliasi KPI" in memo_resp.text


def test_owner_access_guard_blocks_public_upload_but_allows_samples(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("OWNER_ACCESS_CODE", raising=False)
    status_resp = client.get("/api/access/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["upload_locked"] is True

    csv_bytes = b"order_id,order_date,sales_channel,order_total\nO1,2026-01-01,Web,100000\n"
    blocked = client.post(
        "/api/analyze/upload",
        files={"quant_file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert blocked.status_code == 403

    monkeypatch.setenv("OWNER_ACCESS_CODE", "kh-owner-2026")
    bad_code = client.post(
        "/api/analyze/upload",
        files={"quant_file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers={"X-Owner-Code": "wrong"},
    )
    assert bad_code.status_code == 401

    sample_ok = client.post("/api/analyze/sample/swiftbite_capstone")
    assert sample_ok.status_code == 200

    owner_ok = client.post(
        "/api/analyze/upload",
        files={"quant_file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers={"X-Owner-Code": "kh-owner-2026"},
    )
    assert owner_ok.status_code == 200


def test_mismatch_detection_and_upload_and_memo_export():
    csv_bytes = (
        "order_id,order_date,sales_channel,order_total\n"
        "O1,2026-01-01,Web,100000\n"
        "O2,2026-01-10,App,200000\n"
        "O3,2026-01-20,App,150000\n"
    ).encode("utf-8")

    bad_snapshot = [
        {"metric": "Total Orders", "dashboard_value": 5},
        {"metric": "Total GMV", "dashboard_value": 450000},
    ]

    resp = client.post(
        "/api/analyze/upload",
        files={"quant_file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"snapshot_json": json.dumps(bad_snapshot)},
    )
    assert resp.status_code == 200
    payload = resp.json()
    rec = payload["reconciliation"]
    assert rec["overall_gate"] == "FAIL"
    assert rec["mismatched"] == 1
    assert rec["results"][0]["status"] == "MISMATCH"
    assert "diagnosis" in rec["results"][0]

    memo_resp = client.post(
        "/api/memo/export",
        json={
            "dataset_name": "orders.csv",
            "analyst_name": "Nusaibah",
            "reconciliation": rec,
            "hypotheses": [
                {
                    "hypothesis_id": "HYP-001",
                    "category": "Revenue Pillar",
                    "dimension": "sales_channel",
                    "segment": "App",
                    "analyst_status": "accepted",
                    "observed_signal": "App contributed 77.8% of GMV.",
                    "candidate_hypothesis": "Candidate hypothesis: App users place higher basket sizes.",
                    "analyst_note": "Verified against promo log.",
                    "alternative_explanations": ["Small sample (n=3)."],
                    "verification_checks_needed": ["Check full month sample."],
                }
            ],
            "analyst_decision_summary": "Hold scaling promo until dashboard Total Orders mismatch is fixed.",
            "recommended_actions": ["Audit dashboard filter on orders.csv before reporting."],
        },
    )
    assert memo_resp.status_code == 200
    assert "Insight Memo & KPI Reconciliation Brief" in memo_resp.text
    assert "Verified against promo log." in memo_resp.text
