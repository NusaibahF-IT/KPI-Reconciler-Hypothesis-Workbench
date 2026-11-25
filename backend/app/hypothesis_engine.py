"""Gate 2: Domain-Agnostic Business Signal & Hypothesis Generator (Anti-Hallucination)."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

from .reconciler import TRUTHY_STRINGS, _clean_num, _register_df, infer_dataset_roles

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk", "dengan", "pada", "tidak", "tapi",
    "tetapi", "sudah", "belum", "saya", "kami", "kita", "juga", "karena", "ada", "bisa", "lebih",
    "sangat", "masih", "lagi", "the", "and", "for", "with", "this", "that", "was", "were", "are",
    "not", "but", "very", "too", "from", "have", "has", "had", "you", "your", "our", "they", "it",
}

COMPLAINT_KEYWORDS: Dict[str, List[str]] = {
    "Delay / Slowness": ["terlambat", "lama", "telat", "estimasi", "nyampe", "late", "delay", "slow", "lambat"],
    "Quality / Temperature": ["dingin", "basi", "hangat", "cold", "stale", "quality", "kualitas"],
    "Packaging / Damage": ["tumpah", "penyok", "rusak", "kemasan", "packing", "damaged", "broken", "spill"],
    "Cancellation / Tech Issue": ["batal", "dibatalkan", "gagal", "crash", "lemot", "error", "failed", "cancel", "bug"],
    "Pricing / Billing": ["mahal", "refund", "tagihan", "expensive", "overcharged", "billing"],
}


def _check_apple_to_apple_dates(df: pd.DataFrame, date_col: Optional[str]) -> Dict[str, Any]:
    if not date_col or date_col not in df.columns:
        return {
            "has_date_col": False,
            "warning": "No date column detected; time-period normalization skipped.",
        }
    parsed = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if len(parsed) == 0:
        return {
            "has_date_col": False,
            "warning": f"Date column '{date_col}' has no parseable timestamps.",
        }
    min_dt = parsed.min()
    max_dt = parsed.max()
    span_days = max(1, int((max_dt.normalize() - min_dt.normalize()).days) + 1)
    active_days = int(parsed.dt.normalize().nunique())
    return {
        "has_date_col": True,
        "date_col": date_col,
        "min_date": str(min_dt)[:10],
        "max_date": str(max_dt)[:10],
        "span_days": span_days,
        "active_days": active_days,
        "warning": None,
    }


def _extract_top_complaint_themes(texts: pd.Series) -> List[Dict[str, Any]]:
    clean_texts = texts.dropna().astype(str).str.lower()
    if len(clean_texts) == 0:
        return []
    themes: List[Dict[str, Any]] = []
    for theme, kws in COMPLAINT_KEYWORDS.items():
        pat = r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b"
        hits = int(clean_texts.str.contains(pat, regex=True).sum())
        if hits > 0:
            themes.append({"theme": theme, "mentions": hits})

    # Fallback: dynamic frequent token extraction for arbitrary domains
    if not themes:
        tokens: List[str] = []
        for t in clean_texts.tolist():
            for w in re.findall(r"[a-z]{4,}", t):
                if w not in STOPWORDS:
                    tokens.append(w)
        for word, cnt in Counter(tokens).most_common(3):
            if cnt >= 2:
                themes.append({"theme": f"Keyword: {word}", "mentions": cnt})

    themes.sort(key=lambda x: x["mentions"], reverse=True)
    return themes[:3]


def generate_business_hypotheses(
    quant_df: pd.DataFrame,
    sentiment_df: Optional[pd.DataFrame] = None,
    target_metric: Optional[str] = None,
    flag_col: Optional[str] = None,
    selected_dimensions: Optional[List[str]] = None,
    roles: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate domain-agnostic Candidate Business Hypotheses (never final prescriptions)."""
    roles = roles or infer_dataset_roles(quant_df, sentiment_df)
    value_col = target_metric if (target_metric and target_metric in quant_df.columns) else roles.get("value_col")
    active_flag_col = flag_col if (flag_col and flag_col in quant_df.columns) else (None if flag_col == "__none__" else roles.get("flag_col"))
    dimensions = [
        d for d in (selected_dimensions or roles.get("dimensions", []))
        if d in quant_df.columns and d != active_flag_col and d != value_col
    ][:6]

    date_coverage = _check_apple_to_apple_dates(quant_df, roles.get("date_col"))

    con = duckdb.connect(":memory:")
    _register_df(con, "q_tbl", quant_df)

    total_rows = int(len(quant_df))
    hypotheses: List[Dict[str, Any]] = []
    h_seq = 1

    def add_hypothesis(
        category: str,
        signal_strength: str,
        sample_size: int,
        dimension: str,
        segment: str,
        observed_signal: str,
        candidate_hypothesis: str,
        alternative_explanations: List[str],
        verification_checks: List[str],
        metrics: Dict[str, Any],
    ) -> None:
        nonlocal h_seq
        hypotheses.append({
            "hypothesis_id": f"HYP-{h_seq:03d}",
            "category": category,
            "signal_strength": signal_strength,
            "sample_size": int(sample_size),
            "sample_size_flag": "ADEQUATE" if sample_size >= 30 else "LOW_SAMPLE_WARNING",
            "dimension": dimension,
            "segment": segment,
            "observed_signal": observed_signal,
            "candidate_hypothesis": candidate_hypothesis,
            "alternative_explanations": alternative_explanations,
            "verification_checks_needed": verification_checks,
            "supporting_metrics": metrics,
            "analyst_status": "pending_review",
            "analyst_note": "",
        })
        h_seq += 1

    # 1. Value Concentration & Average Gap Hypotheses across dimensions
    overall_total_val = 0.0
    overall_mean_val = 0.0
    if value_col and total_rows > 0:
        qval = f'"{value_col.replace(chr(34), chr(34)*2)}"'
        base_row = con.execute(
            f"SELECT COALESCE(SUM(CAST({qval} AS DOUBLE)), 0), COALESCE(AVG(CAST({qval} AS DOUBLE)), 0) FROM q_tbl WHERE {qval} IS NOT NULL"
        ).fetchone()
        overall_total_val = float(base_row[0] or 0.0)
        overall_mean_val = float(base_row[1] or 0.0)

    dimension_breakdowns: List[Dict[str, Any]] = []
    min_slice_n = max(5, min(15, max(5, total_rows // 10)))

    if value_col and total_rows > 0 and overall_total_val != 0:
        qval = f'"{value_col.replace(chr(34), chr(34)*2)}"'
        for dim in dimensions:
            qdim = f'"{dim.replace(chr(34), chr(34)*2)}"'
            rows = con.execute(
                f"""
                SELECT
                    COALESCE(CAST({qdim} AS VARCHAR), '(Missing)') AS seg,
                    COUNT(*) AS cnt,
                    SUM(CAST({qval} AS DOUBLE)) AS total_v,
                    AVG(CAST({qval} AS DOUBLE)) AS avg_v,
                    MEDIAN(CAST({qval} AS DOUBLE)) AS med_v
                FROM q_tbl
                WHERE {qval} IS NOT NULL
                GROUP BY 1
                ORDER BY total_v DESC
                """
            ).fetchall()
            if len(rows) < 2:
                continue

            breakdown_items = []
            for seg, cnt, tot_v, avg_v, med_v in rows:
                share_pct = round((float(tot_v or 0) / overall_total_val) * 100, 2) if overall_total_val else 0.0
                breakdown_items.append({
                    "segment": seg,
                    "count": int(cnt),
                    "total_value": _clean_num(tot_v),
                    "share_pct": share_pct,
                    "avg_value": _clean_num(avg_v),
                    "median_value": _clean_num(med_v),
                })
            dimension_breakdowns.append({"dimension": dim, "slices": breakdown_items})

            top_slice = breakdown_items[0]
            eligible = [x for x in breakdown_items if x["count"] >= min_slice_n and x["avg_value"] is not None]
            if eligible:
                top_avg = max(eligible, key=lambda x: x["avg_value"])
                lift_pct = round(((top_avg["avg_value"] - overall_mean_val) / abs(overall_mean_val)) * 100, 1) if overall_mean_val else 0.0
                if top_slice["share_pct"] >= 35.0 or lift_pct >= 12.0:
                    add_hypothesis(
                        category="Key Value Driver",
                        signal_strength="Strong" if (top_slice["share_pct"] >= 40.0 or lift_pct >= 20.0) else "Moderate",
                        sample_size=top_avg["count"],
                        dimension=dim,
                        segment=top_avg["segment"],
                        observed_signal=(
                            f"Under '{dim}', segment '{top_avg['segment']}' averages {top_avg['avg_value']:,.2f} for {value_col} "
                            f"({lift_pct:+.1f}% vs overall mean {overall_mean_val:,.2f}) across {top_avg['count']} records, "
                            f"accounting for {top_avg['share_pct']}% of total {value_col}."
                        ),
                        candidate_hypothesis=(
                            f"Candidate hypothesis: '{top_avg['segment']}' acts as a primary driver of {value_col}, potentially due to "
                            f"unit mix, pricing tier, or higher engagement/volume in this segment."
                        ),
                        alternative_explanations=[
                            "Mean may be pulled upward by extreme outliers (compare against median).",
                            "Segment composition may overlap with another confounding dimension (e.g. region or plan tier).",
                        ],
                        verification_checks=[
                            f"Compare median {value_col} ({top_avg['median_value']:,.2f}) vs mean ({top_avg['avg_value']:,.2f}) to rule out outlier skew.",
                            f"Cross-tab '{dim}' against other key dimensions before prioritizing resource allocation.",
                        ],
                        metrics=top_avg,
                    )

            if eligible and len(eligible) >= 2:
                low_avg = min(eligible, key=lambda x: x["avg_value"])
                drop_pct = round(((low_avg["avg_value"] - overall_mean_val) / abs(overall_mean_val)) * 100, 1) if overall_mean_val else 0.0
                if drop_pct <= -12.0:
                    add_hypothesis(
                        category="Underperforming Segment Signal",
                        signal_strength="Moderate",
                        sample_size=low_avg["count"],
                        dimension=dim,
                        segment=low_avg["segment"],
                        observed_signal=(
                            f"Segment '{low_avg['segment']}' under '{dim}' averages {low_avg['avg_value']:,.2f} for {value_col} "
                            f"({drop_pct:.1f}% below overall mean) across {low_avg['count']} records."
                        ),
                        candidate_hypothesis=(
                            f"Candidate hypothesis: Lower {value_col} in '{low_avg['segment']}' may reflect entry-level mix, "
                            f"discount/cost pressure, or process friction within this segment."
                        ),
                        alternative_explanations=[
                            "Segment naturally serves smaller-scale or entry-tier cases.",
                            "External mix differences (e.g. channel, tenure, or geography) may explain the lower average.",
                        ],
                        verification_checks=[
                            f"Check volume/count drivers and secondary metrics for '{low_avg['segment']}'.",
                            "Verify whether lower average coincides with higher failure, churn, or refund rates.",
                        ],
                        metrics=low_avg,
                    )

    # 2. Binary Outcome / Rate Anomaly Hypotheses (works for is_late, is_churned, attrition, etc.)
    delivery_status_col = roles.get("delivery_status_col")
    if active_flag_col and active_flag_col in quant_df.columns and total_rows > 0:
        if "late" in active_flag_col.lower() and delivery_status_col and delivery_status_col in quant_df.columns:
            valid_flag_df = quant_df[
                quant_df[delivery_status_col].astype(str).str.lower().eq("delivered") & quant_df[active_flag_col].notna()
            ].copy()
        else:
            valid_flag_df = quant_df[quant_df[active_flag_col].notna()].copy()

        if len(valid_flag_df) > 0:
            norm_vals = valid_flag_df[active_flag_col].astype(str).str.strip().str.lower().replace({"1.0": "1", "0.0": "0"})
            valid_flag_df["_flag_num"] = norm_vals.isin(TRUTHY_STRINGS).astype(int)
            base_rate = float(valid_flag_df["_flag_num"].mean()) * 100.0

            for dim in dimensions:
                grp = valid_flag_df.groupby(valid_flag_df[dim].fillna("(Missing)").astype(str))["_flag_num"].agg(["count", "sum", "mean"])
                for seg, r in grp.iterrows():
                    cnt = int(r["count"])
                    rate_pct = round(float(r["mean"]) * 100.0, 2)
                    pp_gap = round(rate_pct - base_rate, 2)
                    if cnt >= min_slice_n and (rate_pct >= base_rate * 1.25 or pp_gap >= 6.0):
                        add_hypothesis(
                            category="Outcome Rate Anomaly",
                            signal_strength="Strong" if pp_gap >= 10.0 else "Moderate",
                            sample_size=cnt,
                            dimension=dim,
                            segment=str(seg),
                            observed_signal=(
                                f"Positive rate of '{active_flag_col}' for '{seg}' ({dim}) reached {rate_pct}% "
                                f"({int(r['sum'])}/{cnt} records), which is +{pp_gap} percentage points above baseline ({base_rate:.2f}%)."
                            ),
                            candidate_hypothesis=(
                                f"Candidate hypothesis: '{seg}' experiences elevated '{active_flag_col}' incidence, potentially linked "
                                f"to operational bottlenecks, segment-specific friction, or targeting differences."
                            ),
                            alternative_explanations=[
                                "Sub-segment differences or seasonal clustering could inflate the rate in this slice.",
                                "Sample size or reporting completeness may vary across segments.",
                            ],
                            verification_checks=[
                                f"Inspect secondary operational drivers within '{dim} = {seg}'.",
                                "Check whether the elevated rate persists across multiple time sub-periods.",
                            ],
                            metrics={"record_count": cnt, "flag_true_count": int(r["sum"]), "rate_pct": rate_pct, "baseline_pct": round(base_rate, 2)},
                        )

    # 3. Period-over-Period Run-Rate Shift (Apple-to-Apple Normalized)
    if date_coverage.get("has_date_col") and value_col and date_coverage["span_days"] >= 14:
        dcol = date_coverage["date_col"]
        dt_series = pd.to_datetime(quant_df[dcol], errors="coerce")
        valid_dt_df = quant_df.loc[dt_series.notna()].copy()
        valid_dt_df["_dt"] = dt_series.loc[dt_series.notna()]
        midpoint = valid_dt_df["_dt"].min() + (valid_dt_df["_dt"].max() - valid_dt_df["_dt"].min()) / 2

        p1 = valid_dt_df[valid_dt_df["_dt"] <= midpoint]
        p2 = valid_dt_df[valid_dt_df["_dt"] > midpoint]
        d1 = max(1, int(p1["_dt"].dt.normalize().nunique()))
        d2 = max(1, int(p2["_dt"].dt.normalize().nunique()))

        if len(p1) >= min_slice_n and len(p2) >= min_slice_n:
            run_rate_1 = float(p1[value_col].sum()) / d1
            run_rate_2 = float(p2[value_col].sum()) / d2
            rr_delta_pct = round(((run_rate_2 - run_rate_1) / abs(run_rate_1)) * 100, 1) if run_rate_1 != 0 else 0.0
            if abs(rr_delta_pct) >= 10.0:
                direction = "increased" if rr_delta_pct > 0 else "declined"
                add_hypothesis(
                    category="Period Run-Rate Shift",
                    signal_strength="Strong" if abs(rr_delta_pct) >= 20.0 else "Moderate",
                    sample_size=min(len(p1), len(p2)),
                    dimension=dcol,
                    segment="Period 1 vs Period 2",
                    observed_signal=(
                        f"Normalized daily {value_col} run-rate {direction} by {rr_delta_pct:+.1f}% from Period 1 "
                        f"({run_rate_1:,.2f}/day over {d1} active days) to Period 2 ({run_rate_2:,.2f}/day over {d2} active days)."
                    ),
                    candidate_hypothesis=(
                        f"Candidate hypothesis: Changes in acquisition mix, pricing/campaign cadence, or operational throughput "
                        f"between the two halves may explain the {direction} daily run-rate."
                    ),
                    alternative_explanations=[
                        f"Period 1 ({d1} active days) and Period 2 ({d2} active days) may reflect calendar/seasonality differences.",
                        "One-off outlier records can skew period run-rates.",
                    ],
                    verification_checks=[
                        "Decompose daily run-rate delta into record volume change vs average value per record.",
                        "Compare segment mix shifts between Period 1 and Period 2.",
                    ],
                    metrics={"period1_daily_rate": round(run_rate_1, 2), "period2_daily_rate": round(run_rate_2, 2), "delta_pct": rr_delta_pct, "days_p1": d1, "days_p2": d2},
                )

    # 4. Separate Sentiment / Feedback Layer Convergent Signal (No Forced Join!)
    sentiment_col = roles.get("sentiment_col")
    text_col = roles.get("text_col")
    sent_source = sentiment_df if sentiment_df is not None else quant_df
    if sentiment_col and sentiment_col in sent_source.columns:
        valid_rev = sent_source[
            sent_source[sentiment_col].notna() & (~sent_source[sentiment_col].astype(str).str.lower().isin({"no review", "none", ""}))
        ].copy()
        if len(valid_rev) > 0:
            valid_rev["_is_neg"] = valid_rev[sentiment_col].astype(str).str.upper().str.strip().eq("NEGATIVE").astype(int)
            base_neg_pct = float(valid_rev["_is_neg"].mean()) * 100.0
            shared_dims = [c for c in valid_rev.columns if c in dimensions or c in {"sales_channel", "city_group", "product_category", "cuisine_type"}]
            seen_dims = set()
            for dim in shared_dims:
                if dim in seen_dims or dim not in valid_rev.columns:
                    continue
                seen_dims.add(dim)
                grp = valid_rev.groupby(valid_rev[dim].fillna("(Missing)").astype(str))["_is_neg"].agg(["count", "sum", "mean"])
                for seg, r in grp.iterrows():
                    cnt = int(r["count"])
                    neg_rate = round(float(r["mean"]) * 100.0, 2)
                    gap = round(neg_rate - base_neg_pct, 2)
                    if cnt >= min_slice_n and (neg_rate >= base_neg_pct * 1.2 or gap >= 6.0):
                        themes = []
                        if text_col and text_col in valid_rev.columns:
                            neg_texts = valid_rev.loc[
                                (valid_rev[dim].fillna("(Missing)").astype(str) == str(seg)) & (valid_rev["_is_neg"] == 1),
                                text_col,
                            ]
                            themes = _extract_top_complaint_themes(neg_texts)
                        layer_note = "separate unjoined feedback layer (S9 guardrail)" if sentiment_df is not None else "inline feedback column"
                        add_hypothesis(
                            category="Customer Sentiment Signal",
                            signal_strength="Strong" if gap >= 10.0 else "Moderate",
                            sample_size=cnt,
                            dimension=dim,
                            segment=str(seg),
                            observed_signal=(
                                f"In {layer_note}, '{seg}' ({dim}) shows {neg_rate}% negative sentiment ({int(r['sum'])}/{cnt} entries), "
                                f"+{gap}pp above overall negative rate ({base_neg_pct:.2f}%)."
                                + (f" Recurring themes: {', '.join(t['theme'] + ' (' + str(t['mentions']) + ')' for t in themes)}." if themes else "")
                            ),
                            candidate_hypothesis=(
                                f"Candidate hypothesis: Elevated negative feedback in '{seg}' may reflect recurring service, quality, "
                                f"or expectation gaps in this segment."
                            ),
                            alternative_explanations=[
                                "Response bias: dissatisfied users leave feedback more frequently than satisfied users.",
                                "If feedback layer is separate from primary records, counts do not imply 1-to-1 record linkage.",
                            ],
                            verification_checks=[
                                "Cross-check quantitative outcome/failure metrics in the same segment without forcing invalid joins.",
                                "Manually audit 15-25 negative text samples from this segment.",
                            ],
                            metrics={"review_count": cnt, "negative_count": int(r["sum"]), "negative_rate_pct": neg_rate, "themes": themes},
                        )

    con.close()

    return {
        "target_metric": value_col,
        "active_flag_col": active_flag_col,
        "date_coverage": date_coverage,
        "total_hypotheses": len(hypotheses),
        "hypotheses": hypotheses,
        "dimension_breakdowns": dimension_breakdowns,
    }
