from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

try:
    from .premarket_shared import (
        DEFAULT_PAYLOAD,
        FILTER_CAPABILITY,
        apply_market_scope,
        apply_range_filter,
        build_frontend_rows,
        needs_hist_enrichment,
        normalize_payload,
        save_screen_result,
    )
    from .tushare_provider import (
        fetch_cyq_perf_for_trade_date,
        get_recent_trade_date_text,
        fetch_recent_trade_dates,
        fetch_stock_basic_full,
        fetch_daily_for_trade_date,
        fetch_daily_basic_for_trade_date,
        fetch_daily_history_for_dates,
    )
except ImportError:
    from premarket_shared import (
        DEFAULT_PAYLOAD,
        FILTER_CAPABILITY,
        apply_market_scope,
        apply_range_filter,
        build_frontend_rows,
        needs_hist_enrichment,
        normalize_payload,
        save_screen_result,
    )
    from tushare_provider import (
        fetch_cyq_perf_for_trade_date,
        get_recent_trade_date_text,
        fetch_recent_trade_dates,
        fetch_stock_basic_full,
        fetch_daily_for_trade_date,
        fetch_daily_basic_for_trade_date,
        fetch_daily_history_for_dates,
    )


SNAPSHOT_CACHE_TTL_SECONDS = 300
HISTORY_CACHE_TTL_SECONDS = 900
SNAPSHOT_CACHE: dict[str, Any] = {"expires_at": 0.0, "trade_date": None, "data": None}
HISTORY_CACHE: dict[str, Any] = {"expires_at": 0.0, "trade_dates": None, "data": None}


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _merge_latest_snapshot(trade_date: str) -> pd.DataFrame:
    stock_basic_df = fetch_stock_basic_full()
    daily_df = fetch_daily_for_trade_date(trade_date=trade_date)
    daily_basic_df = fetch_daily_basic_for_trade_date(trade_date=trade_date)
    cyq_perf_df = fetch_cyq_perf_for_trade_date(trade_date=trade_date)

    merged_df = daily_df.merge(daily_basic_df, on=["ts_code", "trade_date"], how="inner")
    merged_df = merged_df.merge(stock_basic_df, on="ts_code", how="left")
    if cyq_perf_df is not None and not cyq_perf_df.empty:
        merged_df = merged_df.merge(cyq_perf_df, on=["ts_code", "trade_date"], how="left")

    merged_df["symbol"] = merged_df["symbol"].astype(str).str.zfill(6)
    merged_df["latest_price"] = pd.to_numeric(merged_df["close"], errors="coerce")
    merged_df["change_pct"] = pd.to_numeric(merged_df["pct_chg"], errors="coerce")
    merged_df["change_amount"] = pd.to_numeric(merged_df["change"], errors="coerce")
    merged_df["volume"] = pd.to_numeric(merged_df["vol"], errors="coerce")
    merged_df["amount"] = pd.to_numeric(merged_df["amount"], errors="coerce") * 1000
    merged_df["amplitude"] = ((pd.to_numeric(merged_df["high"], errors="coerce") - pd.to_numeric(merged_df["low"], errors="coerce")) / pd.to_numeric(merged_df["pre_close"], errors="coerce")) * 100
    merged_df["high_price"] = pd.to_numeric(merged_df["high"], errors="coerce")
    merged_df["low_price"] = pd.to_numeric(merged_df["low"], errors="coerce")
    merged_df["open_price"] = pd.to_numeric(merged_df["open"], errors="coerce")
    merged_df["prev_close"] = pd.to_numeric(merged_df["pre_close"], errors="coerce")
    merged_df["volume_ratio"] = pd.to_numeric(merged_df["volume_ratio"], errors="coerce")
    merged_df["turnover_rate"] = pd.to_numeric(merged_df["turnover_rate"], errors="coerce")
    merged_df["pe_dynamic"] = pd.to_numeric(merged_df["pe"], errors="coerce")
    merged_df["pb_ratio"] = pd.to_numeric(merged_df["pb"], errors="coerce")
    merged_df["total_market_cap"] = pd.to_numeric(merged_df["total_mv"], errors="coerce") * 10000
    merged_df["circulating_market_cap"] = pd.to_numeric(merged_df["circ_mv"], errors="coerce") * 10000
    merged_df["change_pct_60d"] = float("nan")
    merged_df["cost_15pct"] = pd.to_numeric(merged_df.get("cost_15pct"), errors="coerce")
    merged_df["cost_50pct"] = pd.to_numeric(merged_df.get("cost_50pct"), errors="coerce")
    merged_df["cost_85pct"] = pd.to_numeric(merged_df.get("cost_85pct"), errors="coerce")
    merged_df["weight_avg"] = pd.to_numeric(merged_df.get("weight_avg"), errors="coerce")
    merged_df["winner_rate"] = pd.to_numeric(merged_df.get("winner_rate"), errors="coerce")
    merged_df["chip_concentration"] = (
        (merged_df["cost_85pct"] - merged_df["cost_15pct"]) / merged_df["weight_avg"] * 100
    )
    merged_df["price_vs_chip"] = (
        (merged_df["latest_price"] - merged_df["weight_avg"]) / merged_df["weight_avg"] * 100
    )
    merged_df["market"] = merged_df["symbol"].map(lambda symbol: apply_market_scope.__globals__["infer_market"](symbol))
    merged_df["is_st"] = merged_df["name"].fillna("").str.contains("ST", case=False, regex=False)
    merged_df["is_bse"] = merged_df["symbol"].str.startswith(("4", "8", "92"))
    merged_df["list_date"] = pd.to_datetime(merged_df["list_date"], format="%Y%m%d", errors="coerce")
    current_trade_date = pd.to_datetime(trade_date, format="%Y%m%d", errors="coerce")
    merged_df["listing_days"] = (current_trade_date - merged_df["list_date"]).dt.days
    merged_df["trade_date"] = trade_date

    keep_columns = [
        "ts_code",
        "trade_date",
        "symbol",
        "name",
        "industry",
        "market",
        "latest_price",
        "change_pct",
        "change_amount",
        "volume",
        "amount",
        "amplitude",
        "high_price",
        "low_price",
        "open_price",
        "prev_close",
        "volume_ratio",
        "turnover_rate",
        "pe_dynamic",
        "pb_ratio",
        "total_market_cap",
        "circulating_market_cap",
        "change_pct_60d",
        "chip_concentration",
        "winner_rate",
        "price_vs_chip",
        "cost_15pct",
        "cost_50pct",
        "cost_85pct",
        "weight_avg",
        "is_st",
        "is_bse",
        "listing_days",
    ]
    return merged_df[keep_columns].copy()


def fetch_tushare_snapshot(force_refresh: bool = False) -> tuple[pd.DataFrame, str, bool]:
    trade_date = get_recent_trade_date_text()
    now = time.time()
    if (
        not force_refresh
        and SNAPSHOT_CACHE["data"] is not None
        and SNAPSHOT_CACHE["trade_date"] == trade_date
        and now < SNAPSHOT_CACHE["expires_at"]
    ):
        return SNAPSHOT_CACHE["data"].copy(), trade_date, True

    snapshot_df = _merge_latest_snapshot(trade_date)
    SNAPSHOT_CACHE.update(
        {
            "expires_at": now + SNAPSHOT_CACHE_TTL_SECONDS,
            "trade_date": trade_date,
            "data": snapshot_df.copy(),
        }
    )
    return snapshot_df, trade_date, False


def fetch_tushare_history(force_refresh: bool = False, count: int = 70) -> tuple[pd.DataFrame, list[str], bool]:
    trade_dates = fetch_recent_trade_dates(limit=count)
    cache_key = ",".join(trade_dates[-3:]) if trade_dates else ""
    now = time.time()
    if (
        not force_refresh
        and HISTORY_CACHE["data"] is not None
        and HISTORY_CACHE["trade_dates"] == cache_key
        and now < HISTORY_CACHE["expires_at"]
    ):
        return HISTORY_CACHE["data"].copy(), trade_dates, True

    history_df = fetch_daily_history_for_dates(trade_dates)
    HISTORY_CACHE.update(
        {
            "expires_at": now + HISTORY_CACHE_TTL_SECONDS,
            "trade_dates": cache_key,
            "data": history_df.copy(),
        }
    )
    return history_df, trade_dates, False


def apply_fast_filters(df: pd.DataFrame, payload: dict[str, Any]) -> pd.DataFrame:
    working_df = apply_market_scope(df.copy(), payload.get("market_scope", DEFAULT_PAYLOAD["market_scope"]))

    if payload.get("exclude_st", True):
        working_df = working_df[~working_df["is_st"]]
    if payload.get("exclude_bse", True):
        working_df = working_df[~working_df["is_bse"]]
    if payload.get("exclude_paused", True):
        working_df = working_df[working_df["amount"].fillna(0) > 0]

    filters = payload.get("filters", {})
    working_df = apply_range_filter(working_df, "latest_price", filters.get("price_range"))
    working_df = apply_range_filter(working_df, "total_market_cap", filters.get("total_market_cap"))
    working_df = apply_range_filter(working_df, "circulating_market_cap", filters.get("circulating_market_cap"))
    working_df = apply_range_filter(working_df, "change_pct", filters.get("change_pct"))
    working_df = apply_range_filter(working_df, "turnover_rate", filters.get("turnover_rate"))
    working_df = apply_range_filter(working_df, "amount", filters.get("amount"))
    working_df = apply_range_filter(working_df, "amplitude", filters.get("amplitude"))
    working_df = apply_range_filter(working_df, "volume_ratio", filters.get("volume_ratio"))
    working_df = apply_range_filter(working_df, "chip_concentration", filters.get("chip_concentration"))
    working_df = apply_range_filter(working_df, "winner_rate", filters.get("winner_rate"))
    working_df = apply_range_filter(working_df, "price_vs_chip", filters.get("price_vs_chip"))
    return working_df


def _safe_pct_change(current: float, previous: float) -> float:
    if previous in (None, 0) or pd.isna(previous):
        return float("nan")
    return (current / previous - 1) * 100


def _count_consecutive(changes: list[float], positive: bool) -> int:
    count = 0
    for value in reversed(changes):
        if positive and value > 0:
            count += 1
        elif (not positive) and value < 0:
            count += 1
        else:
            break
    return count


def _count_volume_trend(volumes: list[float], increasing: bool) -> int:
    if len(volumes) < 2:
        return 0
    count = 0
    for index in range(len(volumes) - 1, 0, -1):
        current = volumes[index]
        previous = volumes[index - 1]
        if increasing and current > previous:
            count += 1
        elif (not increasing) and current < previous:
            count += 1
        else:
            break
    return count


def compute_hist_features(history_df: pd.DataFrame, latest_snapshot_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame()

    latest_lookup = latest_snapshot_df.set_index("ts_code")
    features: list[dict[str, Any]] = []

    for ts_code, group_df in history_df.groupby("ts_code"):
        working_df = group_df.sort_values("trade_date").reset_index(drop=True)
        if len(working_df) < 20 or ts_code not in latest_lookup.index:
            continue

        latest = working_df.iloc[-1]
        close = _safe_float(latest["close"])
        volumes = working_df["volume"].fillna(0).tolist()
        changes = working_df["change_pct"].fillna(0).tolist()

        ma5 = working_df["close"].tail(5).mean()
        ma10 = working_df["close"].tail(10).mean()
        ma20 = working_df["close"].tail(20).mean()
        ma60 = working_df["close"].tail(min(60, len(working_df))).mean()

        rise_5d = _safe_pct_change(close, working_df["close"].iloc[-6]) if len(working_df) >= 6 else float("nan")
        rise_10d = _safe_pct_change(close, working_df["close"].iloc[-11]) if len(working_df) >= 11 else float("nan")
        high_10d = working_df["high"].tail(10).max()
        high_20d = working_df["high"].tail(20).max()
        high_60d = working_df["high"].tail(min(60, len(working_df))).max()
        low_20d = working_df["low"].tail(20).min()
        pullback_10d = _safe_pct_change(high_10d, close) if not pd.isna(high_10d) else float("nan")
        change_pct_60d = _safe_pct_change(close, working_df["close"].iloc[-61]) if len(working_df) >= 61 else float("nan")

        latest_row = latest_lookup.loc[ts_code]
        features.append(
            {
                "ts_code": ts_code,
                "symbol": latest_row["symbol"],
                "rise_5d_pct": rise_5d,
                "rise_10d_pct": rise_10d,
                "pullback_10d_pct": pullback_10d,
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
                "ma60": ma60,
                "change_pct_60d": change_pct_60d,
                "close_above_ma5_ma10": bool(close >= ma5 and close >= ma10),
                "close_near_ma20": bool(abs(close - ma20) / ma20 <= 0.03) if ma20 else False,
                "breakout_ma20": bool(close >= ma20 and working_df["close"].iloc[-2] < working_df["close"].tail(20).mean()) if len(working_df) >= 21 else False,
                "breakout_ma60": bool(close >= ma60 and working_df["close"].iloc[-2] < working_df["close"].tail(min(60, len(working_df) - 1)).mean()) if len(working_df) >= 61 else False,
                "is_high_20d": bool(close >= high_20d),
                "is_high_60d": bool(close >= high_60d),
                "is_low_20d": bool(close <= low_20d),
                "consecutive_up_days": _count_consecutive(changes[-10:], positive=True),
                "consecutive_down_days": _count_consecutive(changes[-10:], positive=False),
                "volume_expand_days": _count_volume_trend(volumes[-10:], increasing=True),
                "volume_shrink_days": _count_volume_trend(volumes[-10:], increasing=False),
            }
        )

    return pd.DataFrame(features)


def apply_hist_filters(df: pd.DataFrame, payload: dict[str, Any], info: dict[str, Any]) -> pd.DataFrame:
    filters = payload.get("filters", {})
    working_df = df.copy()

    rise_n_days = filters.get("rise_n_days")
    if isinstance(rise_n_days, dict):
        days = int(rise_n_days["days"])
        column = "rise_10d_pct" if days >= 10 else "rise_5d_pct"
        working_df["rise_n_days_value"] = days
        working_df["rise_n_pct"] = working_df[column]
        working_df = apply_range_filter(working_df, column, rise_n_days["bounds"])
        info["applied_filters"].append("rise_n_days")

    pullback_n_days = filters.get("pullback_n_days")
    if isinstance(pullback_n_days, dict):
        days = int(pullback_n_days["days"])
        working_df["pullback_n_days_value"] = days
        working_df["pullback_n_pct"] = working_df["pullback_10d_pct"]
        working_df = apply_range_filter(working_df, "pullback_10d_pct", pullback_n_days["bounds"])
        info["applied_filters"].append("pullback_n_days")

    ma_position = filters.get("ma_position")
    if ma_position == "above_ma5_ma10":
        working_df = working_df[working_df["close_above_ma5_ma10"]]
        info["applied_filters"].append("ma_position")
    elif ma_position == "near_ma20":
        working_df = working_df[working_df["close_near_ma20"]]
        info["applied_filters"].append("ma_position")

    ma_breakout = filters.get("ma_breakout")
    if ma_breakout == "breakout_ma20":
        working_df = working_df[working_df["breakout_ma20"]]
        info["applied_filters"].append("ma_breakout")
    elif ma_breakout == "breakout_ma60":
        working_df = working_df[working_df["breakout_ma60"]]
        info["applied_filters"].append("ma_breakout")

    new_high_low = filters.get("new_high_low")
    if new_high_low == "high_20d":
        working_df = working_df[working_df["is_high_20d"]]
        info["applied_filters"].append("new_high_low")
    elif new_high_low == "high_60d":
        working_df = working_df[working_df["is_high_60d"]]
        info["applied_filters"].append("new_high_low")
    elif new_high_low == "low_20d":
        working_df = working_df[working_df["is_low_20d"]]
        info["applied_filters"].append("new_high_low")

    consecutive = filters.get("consecutive_up_down")
    if isinstance(consecutive, dict):
        column = "consecutive_up_days" if consecutive["direction"] == "up" else "consecutive_down_days"
        working_df = working_df[
            working_df[column].between(consecutive["min_days"], consecutive["max_days"], inclusive="both")
        ]
        info["applied_filters"].append("consecutive_up_down")

    volume_rule = filters.get("volume_expansion_shrink")
    if volume_rule == "volume_expand_2d":
        working_df = working_df[working_df["volume_expand_days"] >= 2]
        info["applied_filters"].append("volume_expansion_shrink")
    elif volume_rule == "volume_shrink_2d":
        working_df = working_df[working_df["volume_shrink_days"] >= 2]
        info["applied_filters"].append("volume_expansion_shrink")

    if payload.get("exclude_new_listing_90d", False) and "listing_days" in working_df.columns:
        working_df = working_df[working_df["listing_days"] > 90]
        info["applied_filters"].append("new_listing_90d")

    return working_df


def score_candidates(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    working_df = df.copy()
    score_columns = ["change_pct", "turnover_rate", "volume_ratio", "amount", "change_pct_60d"]
    for column in score_columns:
        if column not in working_df.columns:
            working_df[column] = 0

    amount_rank = working_df["amount"].rank(pct=True)
    turnover_rank = working_df["turnover_rate"].rank(pct=True)
    volume_rank = working_df["volume_ratio"].rank(pct=True)
    trend_rank = working_df["change_pct_60d"].fillna(0).rank(pct=True)
    daily_rank = working_df["change_pct"].rank(pct=True)

    hist_bonus = pd.Series(0.0, index=working_df.index)
    if "rise_5d_pct" in working_df.columns:
        hist_bonus += working_df["rise_5d_pct"].fillna(0).rank(pct=True) * 5
    if "consecutive_up_days" in working_df.columns:
        hist_bonus += working_df["consecutive_up_days"].fillna(0).rank(pct=True) * 3
    if "breakout_ma20" in working_df.columns:
        hist_bonus += working_df["breakout_ma20"].fillna(False).astype(int) * 2

    if mode == "post":
        score = daily_rank * 28 + turnover_rank * 22 + volume_rank * 20 + amount_rank * 18 + trend_rank * 12 + hist_bonus
    else:
        score = trend_rank * 28 + volume_rank * 24 + turnover_rank * 20 + amount_rank * 16 + daily_rank * 12 + hist_bonus

    working_df["score"] = score.round(0).clip(0, 100)
    working_df = working_df.sort_values(["score", "amount"], ascending=[False, False]).reset_index(drop=True)
    working_df["rank"] = working_df.index + 1
    return working_df


def run_screen(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    merged_payload = normalize_payload(payload)
    mode = merged_payload.get("mode", "pre")

    started_at = time.perf_counter()
    snapshot_df, trade_date, snapshot_cache_hit = fetch_tushare_snapshot()
    fast_df = apply_fast_filters(snapshot_df, merged_payload)
    fast_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)

    enhance_info = {
        "applied": False,
        "candidate_count": 0,
        "success_count": 0,
        "failed_symbols": [],
        "applied_filters": [],
    }
    history_cache_hit = False
    enhance_elapsed_ms = 0.0
    result_base_df = fast_df.copy()

    if needs_hist_enrichment(merged_payload) and not fast_df.empty:
        enhance_started_at = time.perf_counter()
        history_df, _, history_cache_hit = fetch_tushare_history()
        hist_feature_df = compute_hist_features(history_df, snapshot_df)
        enhance_info["applied"] = True
        enhance_info["candidate_count"] = int(len(fast_df))
        enhance_info["success_count"] = int(len(hist_feature_df))
        if not hist_feature_df.empty:
            working_df = fast_df.merge(hist_feature_df, on=["ts_code", "symbol"], how="inner")
            result_base_df = apply_hist_filters(working_df, merged_payload, enhance_info)
        enhance_elapsed_ms = round((time.perf_counter() - enhance_started_at) * 1000, 2)

    scored_df = score_candidates(result_base_df, mode)
    export_file = save_screen_result(scored_df, merged_payload, mode)

    return {
        "mode": mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_sources": ["Tushare daily", "Tushare daily_basic", "AKShare news brief"],
        "unsupported_filters": [item for item in FILTER_CAPABILITY if item["status"] == "requires_extra_source"],
        "market_scope": merged_payload["market_scope"],
        "screen_depth": merged_payload["screen_depth"],
        "first_round_count": int(len(fast_df)),
        "enhanced_count": int(len(result_base_df)),
        "final_result_count": int(min(len(scored_df), 10)),
        "stage_meta": {
            "fast_filter_ms": fast_elapsed_ms,
            "enhancement_ms": enhance_elapsed_ms,
            "spot_cache_hit": snapshot_cache_hit,
            "hist_cache_hit": history_cache_hit,
            "latest_trade_date": trade_date,
            "hist_enhancement": enhance_info,
        },
        "export_file": export_file,
        "applied_payload": merged_payload,
        "results": build_frontend_rows(scored_df, mode),
    }
