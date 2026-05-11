from __future__ import annotations

import math
from typing import Any

import pandas as pd

try:
    from .tushare_provider import get_recent_trade_date_text, get_tushare_client
except ImportError:
    from tushare_provider import get_recent_trade_date_text, get_tushare_client


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _safe_records(df: pd.DataFrame | None, limit: int | None = None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    working_df = df.copy()
    if limit is not None:
        working_df = working_df.head(limit).copy()
    records = working_df.to_dict(orient="records")
    return [
        {key: _sanitize_value(value) for key, value in record.items()}
        for record in records
    ]


def _prepare_hotspot_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df

    working_df = df.copy()

    if "data_type" in working_df.columns:
        working_df = working_df[working_df["data_type"].astype(str) == "热股"].copy()

    if working_df.empty:
        return working_df

    if "rank_time" in working_df.columns:
        working_df["rank_time"] = pd.to_datetime(working_df["rank_time"], errors="coerce")

    sort_columns: list[str] = []
    ascending: list[bool] = []

    if "hot" in working_df.columns:
        sort_columns.append("hot")
        ascending.append(False)
    if "rank_time" in working_df.columns:
        sort_columns.append("rank_time")
        ascending.append(False)
    if "pct_change" in working_df.columns:
        sort_columns.append("pct_change")
        ascending.append(False)

    if sort_columns:
        working_df = working_df.sort_values(sort_columns, ascending=ascending)

    dedupe_key = "ts_code" if "ts_code" in working_df.columns else "ts_name"
    if dedupe_key in working_df.columns:
        working_df = working_df.drop_duplicates(subset=[dedupe_key], keep="first")

    if "rank" in working_df.columns:
        working_df = working_df.sort_values("rank", ascending=True)

    return working_df


def fetch_postclose_facts(trade_date: str | None = None) -> dict[str, Any]:
    resolved_trade_date = trade_date or get_recent_trade_date_text()
    pro = get_tushare_client()

    moneyflow_ind_df = pro.moneyflow_ind_ths(trade_date=resolved_trade_date)
    moneyflow_cnt_df = pro.moneyflow_cnt_ths(trade_date=resolved_trade_date)
    limit_list_df = pro.limit_list_d(trade_date=resolved_trade_date)
    limit_cpt_df = pro.limit_cpt_list(trade_date=resolved_trade_date)
    ths_hot_df = _prepare_hotspot_df(pro.ths_hot(trade_date=resolved_trade_date))
    highest_board = 0
    if limit_cpt_df is not None and not limit_cpt_df.empty:
        if "days" in limit_cpt_df.columns:
            highest_board = int(pd.to_numeric(limit_cpt_df["days"], errors="coerce").fillna(0).max())
        elif "up_stat" in limit_cpt_df.columns:
            extracted = (
                limit_cpt_df["up_stat"]
                .astype(str)
                .str.extract(r"(\d+)")
                .iloc[:, 0]
            )
            highest_board = int(pd.to_numeric(extracted, errors="coerce").fillna(0).max())

    return {
        "trade_date": resolved_trade_date,
        "moneyflow_ind": {
            "rows": int(0 if moneyflow_ind_df is None else len(moneyflow_ind_df)),
            "top_inflow": _safe_records(
                moneyflow_ind_df.sort_values("net_amount", ascending=False) if "net_amount" in moneyflow_ind_df.columns else moneyflow_ind_df,
                limit=8,
            ),
            "top_outflow": _safe_records(
                moneyflow_ind_df.sort_values("net_amount", ascending=True) if "net_amount" in moneyflow_ind_df.columns else moneyflow_ind_df,
                limit=8,
            ),
        },
        "moneyflow_concept": {
            "rows": int(0 if moneyflow_cnt_df is None else len(moneyflow_cnt_df)),
            "top_inflow": _safe_records(
                moneyflow_cnt_df.sort_values("net_amount", ascending=False) if "net_amount" in moneyflow_cnt_df.columns else moneyflow_cnt_df,
                limit=8,
            ),
            "top_outflow": _safe_records(
                moneyflow_cnt_df.sort_values("net_amount", ascending=True) if "net_amount" in moneyflow_cnt_df.columns else moneyflow_cnt_df,
                limit=8,
            ),
        },
        "limit_structure": {
            "rows": int(0 if limit_list_df is None else len(limit_list_df)),
            "top_limit_up": _safe_records(
                limit_list_df.sort_values(["fd_amount", "amount"], ascending=[False, False])
                if limit_list_df is not None and not limit_list_df.empty and "fd_amount" in limit_list_df.columns
                else limit_list_df,
                limit=12,
            ),
            "summary": {
                "limit_up_count": int(0 if limit_list_df is None else len(limit_list_df)),
                "highest_board": highest_board,
            },
        },
        "limit_concepts": {
            "rows": int(0 if limit_cpt_df is None else len(limit_cpt_df)),
            "items": _safe_records(
                limit_cpt_df.sort_values(["days", "up_nums"], ascending=[False, False])
                if limit_cpt_df is not None and not limit_cpt_df.empty and "days" in limit_cpt_df.columns
                else limit_cpt_df,
                limit=12,
            ),
        },
        "hotspots": {
            "rows": int(0 if ths_hot_df is None else len(ths_hot_df)),
            "top_ranked": _safe_records(
                ths_hot_df.sort_values("rank", ascending=True) if ths_hot_df is not None and not ths_hot_df.empty and "rank" in ths_hot_df.columns else ths_hot_df,
                limit=20,
            ),
        },
    }
