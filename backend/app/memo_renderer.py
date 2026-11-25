"""Gate 3: Analyst-Curated 1-Page Insight Memo Renderer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def render_insight_memo_markdown(payload: Dict[str, Any]) -> str:
    """Render an executive 1-page Insight Memo from verified KPIs & analyst-reviewed hypotheses."""
    dataset_name = payload.get("dataset_name", "Dataset")
    analyst_name = payload.get("analyst_name", "Data Analyst")
    reconciliation = payload.get("reconciliation") or {}
    hypotheses: List[Dict[str, Any]] = payload.get("hypotheses") or []
    analyst_summary = payload.get("analyst_decision_summary", "").strip()
    recommended_actions: List[str] = payload.get("recommended_actions") or []

    accepted = [h for h in hypotheses if h.get("analyst_status") == "accepted"]
    needs_data = [h for h in hypotheses if h.get("analyst_status") == "needs_more_data"]
    pending = [h for h in hypotheses if h.get("analyst_status") == "pending_review"]
    chosen = accepted if accepted else (needs_data + pending)[:5]

    lines = [
        f"# Insight Memo & KPI Reconciliation Brief — {dataset_name}",
        f"- **Prepared by:** {analyst_name}",
        f"- **Generated (UTC):** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **KPI Reconciliation Gate:** `{reconciliation.get('overall_gate', 'NOT_RUN')}` "
        f"({reconciliation.get('matched', 0)}/{reconciliation.get('total_assertions', 0)} assertions matched)",
        "",
        "## 1. KPI Verification Summary (Gate 1)",
        "",
    ]

    if reconciliation.get("results"):
        lines.extend([
            "| Metric | Dashboard | Independent (DuckDB) | Diff | Status |",
            "| :--- | ---: | ---: | ---: | :--- |",
        ])
        for row in reconciliation["results"]:
            lines.append(
                f"| {row.get('metric')} | {row.get('dashboard_value')} | {row.get('independent_value')} | "
                f"{row.get('abs_diff')} | **{row.get('status')}** |"
            )
    else:
        lines.append("_No dashboard snapshot assertions were supplied._")

    lines.extend([
        "",
        "## 2. Analyst-Reviewed Business Hypotheses (Gate 2)",
        "",
    ])

    if not chosen:
        lines.append("_No hypotheses selected._")
    else:
        for h in chosen:
            status_label = str(h.get("analyst_status", "pending_review")).upper()
            lines.append(f"### {h.get('hypothesis_id')}: {h.get('category')} — `{h.get('dimension')} = {h.get('segment')}` [{status_label}]")
            lines.append(f"- **Observed Signal:** {h.get('observed_signal')}")
            lines.append(f"- **Candidate Hypothesis:** {h.get('candidate_hypothesis')}")
            if h.get("analyst_note"):
                lines.append(f"- **Analyst Note:** {h.get('analyst_note')}")
            alts = h.get("alternative_explanations") or []
            if alts:
                lines.append(f"- **Alternative Explanations:** {'; '.join(alts)}")
            checks = h.get("verification_checks_needed") or []
            if checks:
                lines.append(f"- **Verification Checks:** {'; '.join(checks)}")
            lines.append("")

    lines.extend([
        "## 3. Analyst Decision & Business Recommendations (Human-in-the-Loop)",
        "",
        analyst_summary or "_To be finalized by the Data Analyst after completing the verification checks above._",
        "",
    ])
    if recommended_actions:
        lines.append("**Proposed Actions:**")
        for idx, act in enumerate(recommended_actions, 1):
            if str(act).strip():
                lines.append(f"{idx}. {act.strip()}")
        lines.append("")

    return "\n".join(lines)
