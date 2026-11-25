"""Gate 3: Analyst-Curated 1-Page Insight Memo Renderer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def render_insight_memo_markdown(payload: Dict[str, Any]) -> str:
    """Render an executive 1-page Insight Memo from verified KPIs & analyst-reviewed hypotheses."""
    is_id = str(payload.get("lang", "en")).lower().startswith("id")
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
        f"# {'Memo Insight & Ringkasan Rekonsiliasi KPI' if is_id else 'Insight Memo & KPI Reconciliation Brief'} — {dataset_name}",
        f"- **{'Disusun oleh' if is_id else 'Prepared by'}:** {analyst_name}",
        f"- **{'Dibuat (UTC)' if is_id else 'Generated (UTC)'}:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **{'Gate Rekonsiliasi KPI' if is_id else 'KPI Reconciliation Gate'}:** `{reconciliation.get('overall_gate', 'NOT_RUN')}` "
        f"({reconciliation.get('matched', 0)}/{reconciliation.get('total_assertions', 0)} {'asersi cocok' if is_id else 'assertions matched'})",
        "",
        f"## 1. {'Ringkasan Verifikasi KPI (Gate 1)' if is_id else 'KPI Verification Summary (Gate 1)'}",
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
        lines.append("_Belum ada snapshot dashboard yang diuji._" if is_id else "_No dashboard snapshot assertions were supplied._")

    lines.extend([
        "",
        f"## 2. {'Hipotesa Bisnis yang Ditinjau Analis (Gate 2)' if is_id else 'Analyst-Reviewed Business Hypotheses (Gate 2)'}",
        "",
    ])

    if not chosen:
        lines.append("_Tidak ada hipotesa yang dipilih._" if is_id else "_No hypotheses selected._")
    else:
        for h in chosen:
            status_label = str(h.get("analyst_status", "pending_review")).upper()
            lines.append(f"### {h.get('hypothesis_id')}: {h.get('category')} — `{h.get('dimension')} = {h.get('segment')}` [{status_label}]")
            lines.append(f"- **{'Sinyal Teramati (Fakta)' if is_id else 'Observed Signal'}:** {h.get('observed_signal')}")
            lines.append(f"- **{'Kandidat Hipotesa' if is_id else 'Candidate Hypothesis'}:** {h.get('candidate_hypothesis')}")
            if h.get("analyst_note"):
                lines.append(f"- **{'Catatan Analis' if is_id else 'Analyst Note'}:** {h.get('analyst_note')}")
            alts = h.get("alternative_explanations") or []
            if alts:
                lines.append(f"- **{'Penjelasan Alternatif' if is_id else 'Alternative Explanations'}:** {'; '.join(alts)}")
            checks = h.get("verification_checks_needed") or []
            if checks:
                lines.append(f"- **{'Cek Verifikasi Lanjutan' if is_id else 'Verification Checks'}:** {'; '.join(checks)}")
            lines.append("")

    lines.extend([
        f"## 3. {'Keputusan Analis & Rekomendasi Bisnis (Human-in-the-Loop)' if is_id else 'Analyst Decision & Business Recommendations (Human-in-the-Loop)'}",
        "",
        analyst_summary or (
            "_Menunggu finalisasi oleh Data Analyst setelah menyelesaikan cek verifikasi di atas._"
            if is_id
            else "_To be finalized by the Data Analyst after completing the verification checks above._"
        ),
        "",
    ])
    if recommended_actions:
        lines.append(f"**{'Usulan Aksi' if is_id else 'Proposed Actions'}:**")
        for idx, act in enumerate(recommended_actions, 1):
            if str(act).strip():
                lines.append(f"{idx}. {act.strip()}")
        lines.append("")

    return "\n".join(lines)
