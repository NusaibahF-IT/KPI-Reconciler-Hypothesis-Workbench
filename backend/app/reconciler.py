"""Gate 1: Independent DuckDB KPI calculation & dashboard assertion reconciliation."""
from __future__ import annotations

import io
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd

TRUTHY_STRINGS = {"true", "1", "yes", "y"}
BINARY_STRINGS = {"true", "false", "1", "0", "yes", "no", "y", "n"}


def _decode_csv_bytes(raw_bytes: bytes) -> pd.DataFrame:
    last_err: Optional[Exception] = None
    for enc in ("utf-8-sig", "utf-8", "latin1", "cp1252"):
        try:
            text = raw_bytes.decode(enc)
            return pd.read_csv(io.StringIO(text))
        except Exception as exc:
            last_err = exc
    raise ValueError(f"Failed to parse CSV file: {last_err}")


def load_csv_or_excel(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in {"xlsx", "xls"}:
        df = pd.read_excel(io.BytesIO(raw_bytes))
    else:
        df = _decode_csv_bytes(raw_bytes)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _clean_num(val: Any) -> Optional[float]:
    if val is None or pd.isna(val):
        return None
    f = float(val)
    return round(f, 4) if math.isfinite(f) else None


def _register_df(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    safe_df = df.copy()
    for c in safe_df.columns:
        if safe_df[c].dtype == "object":
            safe_df[c] = safe_df[c].where(safe_df[c].notna(), None)
    con.register(name, safe_df)


def _is_binary_column(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return True
    non_null = series.dropna()
    if len(non_null) == 0:
        return False
    uniq = {str(v).strip().lower() for v in non_null.unique()}
    # Handle 0.0 / 1.0 floats parsed from CSV
    uniq = {"0" if u == "0.0" else ("1" if u == "1.0" else u) for u in uniq}
    return 1 <= len(uniq) <= 2 and uniq.issubset(BINARY_STRINGS)


def infer_dataset_roles(
    quant_df: pd.DataFrame,
    sentiment_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Auto-detect key analytical roles across arbitrary business domains."""
    cols = list(quant_df.columns)
    lower_map = {c.lower(): c for c in cols}

    # Primary ID column
    id_col = None
    for cand in ("order_id", "transaction_id", "invoice_id", "user_id", "customer_id", "employee_id", "record_id", "id"):
        if cand in lower_map:
            id_col = lower_map[cand]
            break
    if id_col is None:
        for c in cols:
            if c.lower().endswith("_id"):
                id_col = c
                break

    # Binary flag / outcome columns (e.g. is_late, is_churned, attrition, converted)
    binary_flag_cols: List[str] = [c for c in cols if _is_binary_column(quant_df[c])]
    flag_col = None
    for cand in (
        "is_late", "late_flag", "is_delayed",
        "is_churned", "churn", "churned", "attrition",
        "is_cancelled", "is_canceled", "is_returned", "is_fraud",
        "converted", "is_converted", "no_show",
    ):
        if cand in lower_map and lower_map[cand] in binary_flag_cols:
            flag_col = lower_map[cand]
            break
    if flag_col is None:
        for c in binary_flag_cols:
            if c.lower() != "has_review":
                flag_col = c
                break

    # Numeric KPI candidates (exclude pure binary 0/1 flags unless no other numeric exists)
    numeric_cols: List[str] = []
    for c in cols:
        if pd.api.types.is_numeric_dtype(quant_df[c]) and not pd.api.types.is_bool_dtype(quant_df[c]):
            if c not in binary_flag_cols:
                numeric_cols.append(c)
    if not numeric_cols:
        numeric_cols = [
            c for c in cols
            if pd.api.types.is_numeric_dtype(quant_df[c]) and not pd.api.types.is_bool_dtype(quant_df[c])
        ]

    # Default Value KPI column
    value_col = None
    for cand in (
        "net_payment_amount", "order_total", "total_amount", "sales_amount",
        "amount_paid_total", "revenue", "gmv", "profit", "spend", "ad_spend",
        "cost", "price", "salary", "amount", "value",
    ):
        if cand in lower_map and lower_map[cand] in numeric_cols:
            value_col = lower_map[cand]
            break
    if value_col is None:
        for c in numeric_cols:
            if not any(k in c.lower() for k in ("id", "year", "month", "day", "zip")):
                value_col = c
                break
    if value_col is None and numeric_cols:
        value_col = numeric_cols[0]

    # Date column
    date_col = None
    for cand in ("order_date", "order_timestamp", "transaction_date", "created_at", "signup_date", "date"):
        if cand in lower_map:
            date_col = lower_map[cand]
            break
    if date_col is None:
        for c in cols:
            if any(k in c.lower() for k in ("date", "timestamp", "time", "tgl")):
                date_col = c
                break

    delivery_status_col = lower_map.get("delivery_status")
    order_status_col = lower_map.get("order_status")

    # Sentiment columns (either in separate sentiment_df or inline in quant_df)
    sent_source = sentiment_df if sentiment_df is not None else quant_df
    sent_lower = {c.lower(): c for c in sent_source.columns}
    sentiment_col = None
    for cand in ("sentiment_label", "sentiment", "review_sentiment"):
        if cand in sent_lower:
            sentiment_col = sent_lower[cand]
            break

    text_col = None
    for cand in ("clean_text", "review_text", "original_text", "comment", "feedback", "notes", "reason"):
        if cand in sent_lower:
            text_col = sent_lower[cand]
            break

    has_review_col = lower_map.get("has_review")

    # Categorical breakdown dimensions (reasonable cardinality 2..30)
    excluded = {
        id_col, date_col, text_col,
        "customer_key", "customer_id", "restaurant_id", "delivery_id", "courier_id",
    }
    dimensions: List[str] = []
    for c in cols:
        if c in excluded:
            continue
        if pd.api.types.is_numeric_dtype(quant_df[c]) and not pd.api.types.is_bool_dtype(quant_df[c]):
            continue
        nunique = int(quant_df[c].dropna().nunique())
        if 2 <= nunique <= 30:
            dimensions.append(c)

    return {
        "id_col": id_col,
        "value_col": value_col,
        "date_col": date_col,
        "flag_col": flag_col,
        "late_col": flag_col,  # backwards-compatible alias
        "binary_flag_cols": binary_flag_cols,
        "delivery_status_col": delivery_status_col,
        "order_status_col": order_status_col,
        "sentiment_col": sentiment_col,
        "text_col": text_col,
        "has_review_col": has_review_col,
        "sentiment_is_separate_layer": sentiment_df is not None,
        "numeric_cols": numeric_cols,
        "dimensions": dimensions,
    }


def compute_independent_kpis(
    quant_df: pd.DataFrame,
    sentiment_df: Optional[pd.DataFrame] = None,
    roles: Optional[Dict[str, Any]] = None,
    target_metric: Optional[str] = None,
    flag_col: Optional[str] = None,
    slice_col: Optional[str] = None,
    slice_val: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute baseline & slice KPIs independently using DuckDB SQL."""
    roles = roles or infer_dataset_roles(quant_df, sentiment_df)
    q_filtered = quant_df.copy()

    if slice_col and slice_val is not None and slice_col in q_filtered.columns:
        q_filtered = q_filtered[q_filtered[slice_col].astype(str) == str(slice_val)]

    date_col = roles.get("date_col")
    if date_col and date_col in q_filtered.columns and (date_from or date_to):
        parsed_dates = pd.to_datetime(q_filtered[date_col], errors="coerce")
        if date_from:
            q_filtered = q_filtered[parsed_dates >= pd.to_datetime(date_from)]
            parsed_dates = pd.to_datetime(q_filtered[date_col], errors="coerce")
        if date_to:
            q_filtered = q_filtered[parsed_dates <= pd.to_datetime(date_to)]

    con = duckdb.connect(":memory:")
    _register_df(con, "quant_tbl", q_filtered)

    row_count = int(len(q_filtered))
    id_col = roles.get("id_col")
    value_col = target_metric if (target_metric and target_metric in q_filtered.columns) else roles.get("value_col")
    active_flag_col = flag_col if (flag_col and flag_col in q_filtered.columns) else (None if flag_col == "__none__" else roles.get("flag_col"))

    unique_records = row_count
    if id_col and id_col in q_filtered.columns and row_count > 0:
        qid = f'"{id_col.replace(chr(34), chr(34)*2)}"'
        unique_records = int(con.execute(f"SELECT COUNT(DISTINCT {qid}) FROM quant_tbl").fetchone()[0])

    total_val = mean_val = median_val = None
    if value_col and value_col in q_filtered.columns and row_count > 0:
        qval = f'"{value_col.replace(chr(34), chr(34)*2)}"'
        row = con.execute(
            f"""
            SELECT
                SUM(CAST({qval} AS DOUBLE)),
                AVG(CAST({qval} AS DOUBLE)),
                MEDIAN(CAST({qval} AS DOUBLE))
            FROM quant_tbl
            WHERE {qval} IS NOT NULL
            """
        ).fetchone()
        total_val = _clean_num(row[0])
        mean_val = _clean_num(row[1])
        median_val = _clean_num(row[2])

    # Binary flag rate metrics
    delivery_status_col = roles.get("delivery_status_col")
    flag_true_count = None
    flag_valid_count = None
    flag_rate_pct = None

    if active_flag_col and active_flag_col in q_filtered.columns and row_count > 0:
        if "late" in active_flag_col.lower() and delivery_status_col and delivery_status_col in q_filtered.columns:
            valid_mask = (
                q_filtered[delivery_status_col].astype(str).str.lower().eq("delivered")
                & q_filtered[active_flag_col].notna()
            )
        else:
            valid_mask = q_filtered[active_flag_col].notna()
        valid_sub = q_filtered.loc[valid_mask]
        flag_valid_count = int(len(valid_sub))
        if flag_valid_count > 0:
            norm_vals = valid_sub[active_flag_col].astype(str).str.strip().str.lower().replace({"1.0": "1", "0.0": "0"})
            flag_bool = norm_vals.isin(TRUTHY_STRINGS)
            flag_true_count = int(flag_bool.sum())
            flag_rate_pct = round((flag_true_count / flag_valid_count) * 100, 2)

    # Sentiment layer metrics (either separate DF or inline reviews)
    pos_pct = neg_pct = neu_pct = None
    review_count = 0
    review_coverage_pct = None
    sentiment_col = roles.get("sentiment_col")
    has_review_col = roles.get("has_review_col")

    if sentiment_df is not None and sentiment_col and sentiment_col in sentiment_df.columns:
        s_filtered = sentiment_df.copy()
        if slice_col and slice_val is not None and slice_col in s_filtered.columns:
            s_filtered = s_filtered[s_filtered[slice_col].astype(str) == str(slice_val)]
        review_count = int(len(s_filtered))
        if review_count > 0:
            labels = s_filtered[sentiment_col].astype(str).str.upper().str.strip()
            pos_pct = round(float((labels == "POSITIVE").mean()), 4)
            neg_pct = round(float((labels == "NEGATIVE").mean()), 4)
            neu_pct = round(float((labels == "NEUTRAL").mean()), 4)
    elif sentiment_col and sentiment_col in q_filtered.columns and row_count > 0:
        if has_review_col and has_review_col in q_filtered.columns:
            rev_mask = q_filtered[has_review_col].astype(str).str.lower().isin(TRUTHY_STRINGS)
        else:
            rev_mask = q_filtered[sentiment_col].notna() & (~q_filtered[sentiment_col].astype(str).str.lower().isin({"no review", "none", ""}))
        rev_sub = q_filtered.loc[rev_mask]
        review_count = int(len(rev_sub))
        review_coverage_pct = round((review_count / row_count) * 100, 2) if row_count > 0 else 0.0
        if review_count > 0:
            labels = rev_sub[sentiment_col].astype(str).str.upper().str.strip()
            pos_pct = round(float((labels == "POSITIVE").mean()), 4)
            neg_pct = round(float((labels == "NEGATIVE").mean()), 4)
            neu_pct = round(float((labels == "NEUTRAL").mean()), 4)

    con.close()

    # Build clean display KPIs + aliases for snapshot reconciliation
    kpis: Dict[str, Any] = {
        "Total Rows": row_count,
        f"Unique {id_col}" if id_col else "Unique Records": unique_records,
    }
    aliases_extra: Dict[str, Any] = {
        "Total Orders": unique_records,
        "Unique Records": unique_records,
    }
    if total_val is not None and value_col:
        kpis[f"Sum ({value_col})"] = total_val
        kpis[f"Mean ({value_col})"] = mean_val
        kpis[f"Median ({value_col})"] = median_val
        aliases_extra.update({
            "Total GMV": total_val,
            "Net Payment Value": total_val,
            "Average Order Value": mean_val,
            "Median Order Value": median_val,
        })
    if flag_rate_pct is not None and active_flag_col:
        kpis[f"Rate {active_flag_col} (%)"] = flag_rate_pct
        aliases_extra.update({
            "Delivered Valid Count": flag_valid_count,
            "Late Count": flag_true_count,
            "Late Delivery Rate (%)": flag_rate_pct,
        })
    if review_count > 0:
        kpis["Total Reviews"] = review_count
        if review_coverage_pct is not None:
            kpis["Review Coverage (%)"] = review_coverage_pct
        kpis["Positive Review %"] = pos_pct
        kpis["Negative Review %"] = neg_pct
        kpis["Neutral Review %"] = neu_pct

    all_reconcilable = {**kpis, **aliases_extra}

    return {
        "kpis": kpis,
        "all_reconcilable_kpis": all_reconcilable,
        "active_value_col": value_col,
        "active_flag_col": active_flag_col,
        "roles": roles,
        "slice": {
            "slice_col": slice_col,
            "slice_val": slice_val,
            "date_from": date_from,
            "date_to": date_to,
        },
    }


def _normalize_metric_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def reconcile_snapshot(
    independent_kpis: Dict[str, Any],
    snapshot_items: List[Dict[str, Any]],
    quant_df: Optional[pd.DataFrame] = None,
    roles: Optional[Dict[str, Any]] = None,
    tolerance_rel: float = 0.001,
    lang: str = "en",
) -> Dict[str, Any]:
    """Compare dashboard-reported values against independent DuckDB calculations."""
    is_id = str(lang).lower().startswith("id")
    norm_indep: Dict[str, Tuple[str, float]] = {}
    for k, v in independent_kpis.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            norm_indep[_normalize_metric_key(k)] = (k, float(v))

    aliases = {
        "gmv": "totalgmv",
        "totalrevenue": "totalgmv",
        "revenue": "totalgmv",
        "orders": "totalorders",
        "aov": "averageordervalue",
        "laterate": "latedeliveryrate",
        "positivereview": "positivereview",
        "negativereview": "negativereview",
    }

    results: List[Dict[str, Any]] = []
    pass_count = 0
    mismatch_count = 0

    for item in snapshot_items:
        metric_name = str(item.get("metric", "")).strip()
        if not metric_name:
            continue
        raw_dash = item.get("dashboard_value")
        try:
            dash_val = float(raw_dash)
        except (TypeError, ValueError):
            continue

        norm_key = _normalize_metric_key(metric_name)
        lookup_key = aliases.get(norm_key, norm_key)

        if lookup_key not in norm_indep:
            results.append({
                "metric": metric_name,
                "dashboard_value": dash_val,
                "independent_value": None,
                "abs_diff": None,
                "pct_diff": None,
                "status": "NOT_FOUND_IN_DATASET",
                "diagnosis": (
                    "Nama metrik tidak cocok dengan KPI yang dihitung dari dataset saat ini."
                    if is_id
                    else "Metric name did not match any computed KPI from the current dataset."
                ),
            })
            mismatch_count += 1
            continue

        matched_label, indep_val = norm_indep[lookup_key]

        adjusted_indep = indep_val
        unit_note = ""
        if "%" in metric_name or "rate" in metric_name.lower():
            if dash_val <= 1.0 and indep_val > 1.0:
                adjusted_indep = round(indep_val / 100.0, 6)
                unit_note = " (normalisasi % ke rasio)" if is_id else " (normalized % to ratio)"
            elif dash_val > 1.0 and indep_val <= 1.0:
                adjusted_indep = round(indep_val * 100.0, 4)
                unit_note = " (normalisasi rasio ke %)" if is_id else " (normalized ratio to %)"

        abs_diff = round(dash_val - adjusted_indep, 4)
        denom = abs(adjusted_indep) if abs(adjusted_indep) > 1e-9 else 1.0
        rel_diff = abs(abs_diff) / denom
        pct_diff = round(rel_diff * 100, 4)

        is_match = rel_diff <= tolerance_rel or abs(abs_diff) <= 1e-4
        if is_match:
            status = "MATCH"
            pass_count += 1
            diagnosis = (
                f"Cocok dengan perhitungan independen DuckDB ({matched_label}){unit_note}."
                if is_id
                else f"Matched independent DuckDB calculation ({matched_label}){unit_note}."
            )
        else:
            status = "MISMATCH"
            mismatch_count += 1
            diagnosis = _diagnose_mismatch(metric_name, dash_val, adjusted_indep, abs_diff, quant_df, roles, lang=lang)

        results.append({
            "metric": metric_name,
            "matched_kpi": matched_label,
            "dashboard_value": dash_val,
            "independent_value": adjusted_indep,
            "abs_diff": abs_diff,
            "pct_diff": pct_diff,
            "status": status,
            "diagnosis": diagnosis,
        })

    overall_gate = "PASS" if (len(results) > 0 and mismatch_count == 0) else ("FAIL" if mismatch_count > 0 else "NO_ASSERTIONS")

    return {
        "overall_gate": overall_gate,
        "total_assertions": len(results),
        "matched": pass_count,
        "mismatched": mismatch_count,
        "results": results,
    }


def _diagnose_mismatch(
    metric_name: str,
    dash_val: float,
    indep_val: float,
    abs_diff: float,
    quant_df: Optional[pd.DataFrame],
    roles: Optional[Dict[str, Any]],
    lang: str = "en",
) -> str:
    is_id = str(lang).lower().startswith("id")
    if abs(abs_diff) < 1.0:
        return (
            "Selisih pembulatan/presisi desimal kecil (< 1.0). Periksa aturan pembulatan."
            if is_id
            else "Small rounding/decimal precision difference (< 1.0). Check rounding rules."
        )
    if quant_df is not None and roles:
        id_col = roles.get("id_col")
        if id_col and id_col in quant_df.columns and ("order" in metric_name.lower() or "record" in metric_name.lower()):
            row_cnt = len(quant_df)
            uniq_cnt = int(quant_df[id_col].nunique())
            if abs(dash_val - row_cnt) < 1e-4 and row_cnt != uniq_cnt:
                return (
                    f"Dashboard tampaknya menghitung baris mentah ({row_cnt}), bukan nilai unik {id_col} ({uniq_cnt})."
                    if is_id
                    else f"Dashboard appears to count raw rows ({row_cnt}) instead of distinct {id_col} ({uniq_cnt})."
                )
    if "%" in metric_name or "rate" in metric_name.lower():
        return (
            "Diduga ada perbedaan penyebut (denominator), misalnya membagi dengan seluruh baris alih-alih baris valid."
            if is_id
            else "Denominator mismatch suspected (e.g. dividing by all rows instead of valid rows, or unfiltered scope)."
        )
    if dash_val < indep_val:
        return (
            "Nilai dashboard lebih rendah dari baseline independen — periksa filter tanggal/status yang aktif."
            if is_id
            else "Dashboard value is lower than independent baseline — check active date/status filters or excluded records."
        )
    return (
        "Nilai dashboard lebih tinggi dari baseline independen — periksa kemungkinan join duplikat atau baris batal/refund yang belum dikeluarkan."
        if is_id
        else "Dashboard value is higher than independent baseline — check duplicate joins or unexcluded cancelled/refunded rows."
    )
