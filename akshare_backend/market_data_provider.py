from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from .premarket_tushare_screen_service import fetch_tushare_snapshot
except ImportError:
    from premarket_tushare_screen_service import fetch_tushare_snapshot


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_amount_yi(value: float) -> str:
    return f"{value / 1e8:.2f} 亿元"


def fetch_market_snapshot(force_refresh: bool = False) -> dict[str, Any]:
    df, trade_date, cache_hit = fetch_tushare_snapshot(force_refresh=force_refresh)
    working_df = df.copy()

    if working_df.empty:
        return {
            "status": "degraded",
            "message": "Tushare 返回空市场快照。",
            "facts": {},
        }

    up_count = int((working_df["change_pct"] > 0).sum())
    down_count = int((working_df["change_pct"] < 0).sum())
    flat_count = int((working_df["change_pct"] == 0).sum())
    limit_up_count = int((working_df["change_pct"] >= 9.7).sum())
    limit_down_count = int((working_df["change_pct"] <= -9.7).sum())
    turnover_total = float(working_df["amount"].fillna(0).sum())
    avg_change_pct = float(working_df["change_pct"].fillna(0).mean())

    leaders_df = working_df.sort_values(["amount", "change_pct"], ascending=[False, False]).head(5).copy()
    strongest_df = working_df.sort_values("change_pct", ascending=False).head(5).copy()
    weakest_df = working_df.sort_values("change_pct", ascending=True).head(5).copy()

    leaders = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "change_pct": round(_safe_float(row["change_pct"]), 2),
            "amount_yi": round(_safe_float(row["amount"]) / 1e8, 2),
        }
        for _, row in leaders_df.iterrows()
    ]

    strongest = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "change_pct": round(_safe_float(row["change_pct"]), 2),
        }
        for _, row in strongest_df.iterrows()
    ]

    weakest = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "change_pct": round(_safe_float(row["change_pct"]), 2),
        }
        for _, row in weakest_df.iterrows()
    ]

    return {
        "status": "ok",
        "message": "Tushare 市场快照获取成功。",
        "facts": {
            "trade_date": trade_date,
            "cache_hit": cache_hit,
            "universe_count": int(len(working_df)),
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "avg_change_pct": round(avg_change_pct, 2),
            "turnover_total_yi": round(turnover_total / 1e8, 2),
            "turnover_total_text": _format_amount_yi(turnover_total),
            "leaders": leaders,
            "strongest": strongest,
            "weakest": weakest,
        },
    }
