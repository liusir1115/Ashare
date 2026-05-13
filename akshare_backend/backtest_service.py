from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .premarket_shared import PayloadValidationError, infer_market, needs_hist_enrichment, normalize_payload
    from .premarket_tushare_screen_service import apply_fast_filters, apply_hist_filters, compute_hist_features, score_candidates
    from .tushare_provider import (
        fetch_adj_factor_history_by_ranges,
        fetch_cyq_perf_history_for_dates,
        fetch_daily_basic_history_by_ranges,
        fetch_daily_history_by_ranges,
        fetch_stock_basic_full,
        fetch_trade_dates_between,
    )
except ImportError:
    from premarket_shared import PayloadValidationError, infer_market, needs_hist_enrichment, normalize_payload
    from premarket_tushare_screen_service import apply_fast_filters, apply_hist_filters, compute_hist_features, score_candidates
    from tushare_provider import (
        fetch_adj_factor_history_by_ranges,
        fetch_cyq_perf_history_for_dates,
        fetch_daily_basic_history_by_ranges,
        fetch_daily_history_by_ranges,
        fetch_stock_basic_full,
        fetch_trade_dates_between,
    )


BACKTEST_RESULT_DIR = Path(__file__).resolve().parent.parent / "result" / "backtests"
BACKTEST_CACHE_DIR = BACKTEST_RESULT_DIR / "cache"
LOOKBACK_TRADE_DAYS = 80
DEFAULT_HIST_FEATURE_LOOKBACK_DAYS = 65
SUPPORTED_HISTORY_YEARS = {1, 3, 5}
SUPPORTED_HOLDING_DAYS = {1, 3, 5}
SUPPORTED_TOP_N = {5, 10, 20}
SUPPORTED_ADJ_TYPES = {"qfq"}
SUPPORTED_EXECUTION_MODES = {"fast", "full"}
FAST_MODE_MAX_SELECTIONS = 3
FAST_MODE_EXIT_PADDING_DAYS = 4
MIN_USEFUL_SAMPLE_TRADES = 12
MIN_USEFUL_SAMPLE_CYCLES = 3


@dataclass(slots=True)
class CostModel:
    buy_fee: float = 0.0003
    sell_fee: float = 0.0003
    sell_tax: float = 0.001
    slippage: float = 0.0005


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _default_backtest_payload() -> dict[str, Any]:
    return {
        "screen_payload": normalize_payload(
            {
                "mode": "pre",
                "screen_depth": "full",
                "market_scope": "沪深主板 + 创业板",
                "exclude_st": True,
                "exclude_paused": True,
                "exclude_bse": True,
                "exclude_new_listing_90d": True,
                "filters": {},
            }
        ),
        "history_years": 3,
        "holding_days": 3,
        "top_n": 10,
        "adj_type": "qfq",
        "execution_mode": "fast",
        "costs": {
            "buy_fee": 0.0003,
            "sell_fee": 0.0003,
            "sell_tax": 0.001,
            "slippage": 0.0005,
        },
        "constraints": {
            "skip_one_word_limit_up_buy": True,
            "skip_limit_down_sell": True,
            "skip_suspended": True,
            "skip_st": True,
            "skip_new_listing": True,
        },
    }


def normalize_backtest_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = _default_backtest_payload()
    payload = payload or {}

    screen_payload = normalize_payload(payload.get("screen_payload") or payload.get("payload") or {})
    history_years = int(payload.get("history_years", defaults["history_years"]))
    holding_days = int(payload.get("holding_days", defaults["holding_days"]))
    top_n = int(payload.get("top_n", defaults["top_n"]))
    adj_type = str(payload.get("adj_type", defaults["adj_type"])).strip().lower() or "qfq"
    execution_mode = str(payload.get("execution_mode", defaults["execution_mode"])).strip().lower() or "fast"

    if history_years not in SUPPORTED_HISTORY_YEARS:
        raise PayloadValidationError("history_years 只支持 1 / 3 / 5。")
    if holding_days not in SUPPORTED_HOLDING_DAYS:
        raise PayloadValidationError("holding_days 只支持 1 / 3 / 5。")
    if top_n not in SUPPORTED_TOP_N:
        raise PayloadValidationError("top_n 只支持 5 / 10 / 20。")
    if adj_type not in SUPPORTED_ADJ_TYPES:
        raise PayloadValidationError("adj_type 首版只支持 qfq。")
    if execution_mode not in SUPPORTED_EXECUTION_MODES:
        raise PayloadValidationError("execution_mode 只支持 fast / full。")

    raw_costs = payload.get("costs") or {}
    costs = CostModel(
        buy_fee=float(raw_costs.get("buy_fee", defaults["costs"]["buy_fee"])),
        sell_fee=float(raw_costs.get("sell_fee", defaults["costs"]["sell_fee"])),
        sell_tax=float(raw_costs.get("sell_tax", defaults["costs"]["sell_tax"])),
        slippage=float(raw_costs.get("slippage", defaults["costs"]["slippage"])),
    )

    constraints = defaults["constraints"].copy()
    constraints.update(payload.get("constraints") or {})

    return {
        "screen_payload": screen_payload,
        "history_years": history_years,
        "holding_days": holding_days,
        "top_n": top_n,
        "adj_type": adj_type,
        "execution_mode": execution_mode,
        "costs": costs,
        "constraints": {key: bool(value) for key, value in constraints.items()},
    }


def _resolve_trade_window(history_years: int) -> tuple[list[str], list[str], str, str]:
    end_date = datetime.now().strftime("%Y%m%d")
    start_dt = datetime.now() - timedelta(days=history_years * 370)
    start_date = start_dt.strftime("%Y%m%d")
    lookup_start = (start_dt - timedelta(days=LOOKBACK_TRADE_DAYS * 2)).strftime("%Y%m%d")

    all_trade_dates = fetch_trade_dates_between(lookup_start, end_date)
    active_trade_dates = [item for item in all_trade_dates if item >= start_date]
    if len(active_trade_dates) < 30:
        raise PayloadValidationError("当前历史窗口内可用交易日太少，无法完成回测。建议扩大历史窗口后再试。")
    return all_trade_dates, active_trade_dates, start_date, end_date


def _needs_cyq_payload(screen_payload: dict[str, Any]) -> bool:
    filters = screen_payload.get("filters", {})
    return any(filters.get(key) not in (None, "", [], {}) for key in ("chip_concentration", "winner_rate", "price_vs_chip"))


def _build_cache_key(trade_dates: list[str], include_cyq: bool, adj_type: str) -> str:
    start = trade_dates[0]
    end = trade_dates[-1]
    return f"{start}_{end}_{adj_type}_{'cyq' if include_cyq else 'base'}"


def _sample_selection_indices(selection_indices: list[int], execution_mode: str) -> list[int]:
    if execution_mode != "fast" or len(selection_indices) <= FAST_MODE_MAX_SELECTIONS:
        return selection_indices
    return selection_indices[-FAST_MODE_MAX_SELECTIONS:]


def _estimate_hist_lookback_days(screen_payload: dict[str, Any]) -> int:
    filters = screen_payload.get("filters") or {}
    lookback_days = 10

    for key in ("rise_n_days", "pullback_n_days"):
        value = filters.get(key)
        if isinstance(value, dict):
            lookback_days = max(lookback_days, int(value.get("days") or 0) + 2)

    ma_breakout = filters.get("ma_breakout")
    if ma_breakout == "breakout_ma60":
        lookback_days = max(lookback_days, 61)
    elif ma_breakout == "breakout_ma20":
        lookback_days = max(lookback_days, 21)

    ma_position = filters.get("ma_position")
    if ma_position == "near_ma20":
        lookback_days = max(lookback_days, 20)
    elif ma_position == "above_ma5_ma10":
        lookback_days = max(lookback_days, 10)

    new_high_low = filters.get("new_high_low")
    if new_high_low == "high_60d":
        lookback_days = max(lookback_days, 60)
    elif new_high_low in {"high_20d", "low_20d"}:
        lookback_days = max(lookback_days, 20)

    if filters.get("volume_expansion_shrink") in {"volume_expand_2d", "volume_shrink_2d"}:
        lookback_days = max(lookback_days, 10)

    if isinstance(filters.get("consecutive_up_down"), dict):
        lookback_days = max(lookback_days, 10)

    return min(max(lookback_days, 10), DEFAULT_HIST_FEATURE_LOOKBACK_DAYS)


def _build_required_trade_dates(
    active_trade_dates: list[str],
    selection_indices: list[int],
    holding_days: int,
    hist_lookback_days: int,
) -> list[str]:
    required_indices: set[int] = set()
    for selection_index in selection_indices:
        start_index = max(0, selection_index - hist_lookback_days)
        end_index = min(len(active_trade_dates) - 1, selection_index + holding_days + FAST_MODE_EXIT_PADDING_DAYS)
        required_indices.update(range(start_index, end_index + 1))
    return [active_trade_dates[index] for index in sorted(required_indices)]


def _apply_qfq_prices(panel_df: pd.DataFrame) -> pd.DataFrame:
    if "adj_factor" not in panel_df.columns:
        return panel_df

    latest_factor = (
        panel_df.dropna(subset=["adj_factor"])
        .sort_values(["ts_code", "trade_date"])
        .groupby("ts_code")["adj_factor"]
        .last()
        .rename("latest_adj_factor")
    )
    panel_df = panel_df.merge(latest_factor, on="ts_code", how="left")
    ratio = panel_df["adj_factor"] / panel_df["latest_adj_factor"]

    for column in ("open", "high", "low", "close", "pre_close"):
        panel_df[column] = pd.to_numeric(panel_df[column], errors="coerce") * ratio

    return panel_df


def _build_market_panel(trade_dates: list[str], include_cyq: bool, adj_type: str) -> pd.DataFrame:
    _ensure_dir(BACKTEST_CACHE_DIR)
    cache_file = BACKTEST_CACHE_DIR / f"{_build_cache_key(trade_dates, include_cyq, adj_type)}.pkl"
    if cache_file.exists():
        return pd.read_pickle(cache_file)

    stock_basic_df = fetch_stock_basic_full().copy()
    daily_df = fetch_daily_history_by_ranges(trade_dates)
    daily_basic_df = fetch_daily_basic_history_by_ranges(trade_dates)
    adj_factor_df = fetch_adj_factor_history_by_ranges(trade_dates)

    merged_df = daily_df.merge(daily_basic_df, on=["ts_code", "trade_date"], how="left")
    merged_df = merged_df.merge(stock_basic_df, on="ts_code", how="left")
    merged_df = merged_df.merge(adj_factor_df, on=["ts_code", "trade_date"], how="left")

    if include_cyq:
        cyq_df = fetch_cyq_perf_history_for_dates(trade_dates)
        if cyq_df is not None and not cyq_df.empty:
            merged_df = merged_df.merge(cyq_df, on=["ts_code", "trade_date"], how="left")

    if adj_type == "qfq":
        merged_df = _apply_qfq_prices(merged_df)

    merged_df["symbol"] = merged_df["symbol"].astype(str).str.zfill(6)
    merged_df["latest_price"] = pd.to_numeric(merged_df["close"], errors="coerce")
    merged_df["change_pct"] = pd.to_numeric(merged_df["change_pct"], errors="coerce")
    merged_df["change_amount"] = pd.to_numeric(merged_df["change"], errors="coerce")
    merged_df["volume"] = pd.to_numeric(merged_df["volume"], errors="coerce")
    merged_df["amount"] = pd.to_numeric(merged_df["amount"], errors="coerce")
    merged_df["amplitude"] = (
        (pd.to_numeric(merged_df["high"], errors="coerce") - pd.to_numeric(merged_df["low"], errors="coerce"))
        / pd.to_numeric(merged_df["pre_close"], errors="coerce")
    ) * 100
    merged_df["high_price"] = pd.to_numeric(merged_df["high"], errors="coerce")
    merged_df["low_price"] = pd.to_numeric(merged_df["low"], errors="coerce")
    merged_df["open_price"] = pd.to_numeric(merged_df["open"], errors="coerce")
    merged_df["prev_close"] = pd.to_numeric(merged_df["pre_close"], errors="coerce")
    merged_df["volume_ratio"] = pd.to_numeric(merged_df["volume_ratio"], errors="coerce")
    merged_df["turnover_rate"] = pd.to_numeric(merged_df["turnover_rate"], errors="coerce")
    merged_df["pe_dynamic"] = pd.to_numeric(merged_df.get("pe"), errors="coerce")
    merged_df["pb_ratio"] = pd.to_numeric(merged_df.get("pb"), errors="coerce")
    merged_df["total_market_cap"] = pd.to_numeric(merged_df.get("total_mv"), errors="coerce") * 10000
    merged_df["circulating_market_cap"] = pd.to_numeric(merged_df.get("circ_mv"), errors="coerce") * 10000
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
    merged_df["market"] = merged_df["symbol"].map(infer_market)
    merged_df["is_st"] = merged_df["name"].fillna("").str.contains("ST", case=False, regex=False)
    merged_df["is_bse"] = merged_df["symbol"].str.startswith(("4", "8", "92"))
    merged_df["list_date"] = pd.to_datetime(merged_df["list_date"], format="%Y%m%d", errors="coerce")
    merged_df["listing_days"] = (merged_df["trade_date"] - merged_df["list_date"]).dt.days

    panel_df = merged_df.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    panel_df.to_pickle(cache_file)
    return panel_df


def _limit_pct_for_market(market: str) -> float:
    if market in {"创业板", "科创板"}:
        return 20.0
    if market == "北交所":
        return 30.0
    return 10.0


def _is_one_word_limit_up(row: pd.Series) -> bool:
    limit = _limit_pct_for_market(str(row.get("market", "")))
    values = [row.get("open_price"), row.get("high_price"), row.get("low_price"), row.get("latest_price")]
    if any(pd.isna(value) for value in values):
        return False
    return bool(abs(row["change_pct"]) >= limit - 0.2 and values.count(values[0]) == len(values) and row["change_pct"] > 0)


def _is_limit_down_locked(row: pd.Series) -> bool:
    limit = _limit_pct_for_market(str(row.get("market", "")))
    values = [row.get("open_price"), row.get("high_price"), row.get("low_price"), row.get("latest_price")]
    if any(pd.isna(value) for value in values):
        return False
    return bool(abs(row["change_pct"]) >= limit - 0.2 and values.count(values[0]) == len(values) and row["change_pct"] < 0)


def _is_tradeable_for_buy(row: pd.Series, constraints: dict[str, bool]) -> bool:
    if constraints.get("skip_suspended", True) and _safe_float(row.get("amount")) <= 0:
        return False
    if constraints.get("skip_st", True) and bool(row.get("is_st")):
        return False
    if constraints.get("skip_one_word_limit_up_buy", True) and _is_one_word_limit_up(row):
        return False
    return True


def _find_exit_row(
    panel_lookup: dict[tuple[str, pd.Timestamp], pd.Series],
    ts_code: str,
    trade_dates: list[pd.Timestamp],
    start_index: int,
    constraints: dict[str, bool],
) -> tuple[pd.Series | None, pd.Timestamp | None]:
    for index in range(start_index, len(trade_dates)):
        date_value = trade_dates[index]
        row = panel_lookup.get((ts_code, date_value))
        if row is None:
            continue
        if constraints.get("skip_suspended", True) and _safe_float(row.get("amount")) <= 0:
            continue
        if constraints.get("skip_limit_down_sell", True) and _is_limit_down_locked(row):
            continue
        return row, date_value
    return None, None


def _compute_trade_return(buy_price: float, sell_price: float, costs: CostModel) -> float:
    if not buy_price or not sell_price or pd.isna(buy_price) or pd.isna(sell_price):
        return float("nan")
    buy_cash = buy_price * (1 + costs.buy_fee + costs.slippage)
    sell_cash = sell_price * (1 - costs.sell_fee - costs.sell_tax - costs.slippage)
    return sell_cash / buy_cash - 1


def _compute_max_drawdown(curve: list[float]) -> float:
    peak = 1.0
    max_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1)
    return max_drawdown


def _build_ascii_curve(points: list[float], width: int = 48) -> str:
    if not points:
        return ""
    sample = points if len(points) <= width else [points[int(i * (len(points) - 1) / (width - 1))] for i in range(width)]
    min_value = min(sample)
    max_value = max(sample)
    if math.isclose(min_value, max_value):
        return "█" * len(sample)
    bars = "▁▂▃▄▅▆▇█"
    chars = []
    for value in sample:
        ratio = (value - min_value) / (max_value - min_value)
        index = min(len(bars) - 1, max(0, int(round(ratio * (len(bars) - 1)))))
        chars.append(bars[index])
    return "".join(chars)


def _select_candidates_for_day(
    panel_df: pd.DataFrame,
    trade_date: pd.Timestamp,
    screen_payload: dict[str, Any],
) -> pd.DataFrame:
    snapshot_df = panel_df[panel_df["trade_date"] == trade_date].copy()
    if snapshot_df.empty:
        return pd.DataFrame()

    filtered_df = apply_fast_filters(snapshot_df, screen_payload)
    if filtered_df.empty:
        return filtered_df

    if needs_hist_enrichment(screen_payload):
        history_window_df = panel_df[panel_df["trade_date"] <= trade_date].copy()
        hist_feature_df = compute_hist_features(history_window_df, snapshot_df)
        if hist_feature_df.empty:
            return pd.DataFrame()
        merged_df = filtered_df.merge(hist_feature_df, on=["ts_code", "symbol"], how="inner")
        filtered_df = apply_hist_filters(
            merged_df,
            screen_payload,
            {
                "applied_filters": [],
                "applied": True,
                "candidate_count": int(len(filtered_df)),
                "success_count": int(len(hist_feature_df)),
                "failed_symbols": [],
            },
        )

    if filtered_df.empty:
        return filtered_df
    return score_candidates(filtered_df, "pre")


def _summarize_strategy(
    screen_payload: dict[str, Any],
    top_n: int,
    holding_days: int,
    history_years: int,
    execution_mode: str,
) -> list[str]:
    filters = screen_payload.get("filters", {})
    summary = [
        f"历史窗口 {history_years} 年",
        f"持有周期 {holding_days} 天",
        f"每轮取前 {top_n} 只",
        f"执行模式 {'快速验证' if execution_mode == 'fast' else '完整回测'}",
    ]
    if screen_payload.get("market_scope"):
        summary.append(f"股票范围 {screen_payload['market_scope']}")
    for key, value in filters.items():
        if value in (None, "", [], {}):
            continue
        summary.append(f"{key}: {value}")
    return summary[:12]


def _build_sample_guidance(config: dict[str, Any], summary: dict[str, Any], screen_payload: dict[str, Any]) -> list[str]:
    guidance: list[str] = []
    trade_count = int(summary.get("trade_count") or 0)
    cycle_count = int(summary.get("cycle_count") or 0)
    filters = screen_payload.get("filters") or {}

    if trade_count >= MIN_USEFUL_SAMPLE_TRADES and cycle_count >= MIN_USEFUL_SAMPLE_CYCLES:
        return guidance

    if config["execution_mode"] == "fast":
        guidance.append("当前是快速验证模式，样本偏少时建议再跑一次完整回测，确认这套条件在完整历史里的稳定性。")
    else:
        guidance.append("当前策略命中样本偏少，结果可以参考，但统计稳定性仍然不足。")

    if config["history_years"] < 5:
        guidance.append(f"可先把历史窗口从 {config['history_years']} 年扩大到 5 年，观察样本量是否明显增加。")

    if config["top_n"] < 20:
        guidance.append(f"可将每轮取前 {config['top_n']} 只放宽到 20 只，避免候选池过窄。")

    chip_filters = [key for key in ("chip_concentration", "winner_rate", "price_vs_chip") if filters.get(key) not in (None, "", [], {})]
    if chip_filters:
        guidance.append("当前启用了筹码类条件。如果样本仍偏少，先放宽筹码区间，再保留一个突破类条件验证方向。")

    hist_filters = [key for key in ("rise_n_days", "pullback_n_days", "new_high_low", "ma_breakout", "ma_position", "volume_expansion_shrink") if filters.get(key) not in (None, "", [], {})]
    if len(hist_filters) >= 3:
        guidance.append("当前历史行为条件较多，建议先保留 1 到 2 个核心条件，再逐步叠加。")

    return guidance[:4]


def run_backtest(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    started_at = time.perf_counter()
    config = normalize_backtest_payload(payload)
    screen_payload = config["screen_payload"]
    costs: CostModel = config["costs"]
    constraints = config["constraints"]

    _, active_trade_dates, start_date, end_date = _resolve_trade_window(config["history_years"])
    include_cyq = _needs_cyq_payload(screen_payload)
    active_timestamps = pd.to_datetime(active_trade_dates, format="%Y%m%d", errors="coerce").tolist()

    hist_lookback_days = _estimate_hist_lookback_days(screen_payload)
    warmup_index = min(max(hist_lookback_days + 1, 10), max(len(active_timestamps) - 2, 1))
    last_selection_index = len(active_timestamps) - config["holding_days"] - 1
    if last_selection_index <= 0:
        raise PayloadValidationError("当前历史窗口无法形成有效回测区间，请扩大历史窗口后再试。")

    selection_start = min(warmup_index, max(last_selection_index - 1, 0))
    full_selection_indices = list(range(selection_start, last_selection_index + 1, config["holding_days"]))
    if not full_selection_indices:
        full_selection_indices = [last_selection_index]

    selection_indices = _sample_selection_indices(full_selection_indices, config["execution_mode"])
    required_trade_dates = _build_required_trade_dates(
        active_trade_dates,
        selection_indices,
        config["holding_days"],
        hist_lookback_days,
    )

    fetch_started_at = time.perf_counter()
    panel_df = _build_market_panel(required_trade_dates, include_cyq=include_cyq, adj_type=config["adj_type"])
    panel_df = panel_df[panel_df["trade_date"].isin(pd.to_datetime(required_trade_dates, format="%Y%m%d", errors="coerce"))].copy()
    fetch_elapsed_ms = round((time.perf_counter() - fetch_started_at) * 1000, 2)

    panel_lookup = {(str(row["ts_code"]), row["trade_date"]): row for _, row in panel_df.iterrows()}

    equity = 1.0
    equity_curve: list[dict[str, Any]] = []
    drawdown_curve: list[dict[str, Any]] = []
    yearly_return_map: dict[str, float] = {}
    cycle_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_candidates = 0
    empty_cycles = 0

    compute_started_at = time.perf_counter()
    for selection_index in selection_indices:
        selection_date = active_timestamps[selection_index]
        buy_date = active_timestamps[min(selection_index + 1, len(active_timestamps) - 1)]
        planned_exit_index = min(selection_index + config["holding_days"], len(active_timestamps) - 1)
        candidate_df = _select_candidates_for_day(panel_df, selection_date, screen_payload)
        total_candidates += int(len(candidate_df))

        if candidate_df.empty:
            empty_cycles += 1
            equity_curve.append({"date": selection_date.strftime("%Y-%m-%d"), "equity": round(equity, 6)})
            drawdown_curve.append(
                {
                    "date": selection_date.strftime("%Y-%m-%d"),
                    "drawdown_pct": round(_compute_max_drawdown([item["equity"] for item in equity_curve]) * 100, 2),
                }
            )
            continue

        picked_df = candidate_df.head(config["top_n"]).copy()
        cycle_trade_returns: list[float] = []
        cycle_names: list[str] = []

        for _, row in picked_df.iterrows():
            ts_code = str(row["ts_code"])
            buy_row = panel_lookup.get((ts_code, buy_date))
            if buy_row is None or not _is_tradeable_for_buy(buy_row, constraints):
                continue

            exit_row, actual_exit_date = _find_exit_row(panel_lookup, ts_code, active_timestamps, planned_exit_index, constraints)
            if exit_row is None or actual_exit_date is None:
                continue

            buy_price = _safe_float(buy_row.get("open_price"))
            sell_price = _safe_float(exit_row.get("latest_price"))
            trade_return = _compute_trade_return(buy_price, sell_price, costs)
            if pd.isna(trade_return):
                continue

            holding_days_actual = int((actual_exit_date - buy_date).days)
            cycle_trade_returns.append(trade_return)
            cycle_names.append(str(row.get("name", ts_code)))
            trade_rows.append(
                {
                    "stock": str(row.get("name", ts_code)),
                    "code": str(row.get("symbol", "")).zfill(6),
                    "select_date": selection_date.strftime("%Y-%m-%d"),
                    "buy_date": buy_date.strftime("%Y-%m-%d"),
                    "sell_date": actual_exit_date.strftime("%Y-%m-%d"),
                    "buy_price": round(buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "return_pct": round(trade_return * 100, 2),
                    "holding_days": holding_days_actual,
                    "score": round(_safe_float(row.get("score")), 2),
                }
            )

        if not cycle_trade_returns:
            empty_cycles += 1
            equity_curve.append({"date": selection_date.strftime("%Y-%m-%d"), "equity": round(equity, 6)})
            drawdown_curve.append(
                {
                    "date": selection_date.strftime("%Y-%m-%d"),
                    "drawdown_pct": round(_compute_max_drawdown([item["equity"] for item in equity_curve]) * 100, 2),
                }
            )
            continue

        cycle_return = sum(cycle_trade_returns) / len(cycle_trade_returns)
        equity *= 1 + cycle_return
        exit_date = max(item["sell_date"] for item in trade_rows[-len(cycle_trade_returns):])
        exit_year = str(exit_date)[:4]
        yearly_return_map[exit_year] = (1 + yearly_return_map.get(exit_year, 0.0)) * (1 + cycle_return) - 1

        cycle_rows.append(
            {
                "selection_date": selection_date.strftime("%Y-%m-%d"),
                "buy_date": buy_date.strftime("%Y-%m-%d"),
                "exit_date": exit_date,
                "picked_count": int(len(cycle_trade_returns)),
                "cycle_return_pct": round(cycle_return * 100, 2),
                "stocks": cycle_names[:6],
            }
        )
        equity_curve.append({"date": exit_date, "equity": round(equity, 6)})
        drawdown_curve.append(
            {
                "date": exit_date,
                "drawdown_pct": round(_compute_max_drawdown([item["equity"] for item in equity_curve]) * 100, 2),
            }
        )

    cycle_returns = [row["cycle_return_pct"] / 100 for row in cycle_rows]
    positive_returns = [value for value in cycle_returns if value > 0]
    negative_returns = [value for value in cycle_returns if value < 0]
    trade_count = len(trade_rows)
    avg_holding_days = round(sum(row["holding_days"] for row in trade_rows) / trade_count, 2) if trade_count else 0.0

    cumulative_return = equity - 1
    if trade_rows:
        evaluated_start_dt = min(pd.to_datetime(row["buy_date"]) for row in trade_rows)
        evaluated_end_dt = max(pd.to_datetime(row["sell_date"]) for row in trade_rows)
    elif selection_indices:
        evaluated_start_dt = active_timestamps[selection_indices[0]]
        evaluated_end_dt = active_timestamps[min(len(active_timestamps) - 1, selection_indices[-1] + config["holding_days"])]
    else:
        evaluated_start_dt = pd.to_datetime(start_date)
        evaluated_end_dt = pd.to_datetime(end_date)

    trade_span_days = max(1, int((evaluated_end_dt - evaluated_start_dt).days))
    annual_return = pow(max(equity, 1e-9), 365 / trade_span_days) - 1 if equity > 0 else -1
    max_drawdown = _compute_max_drawdown([item["equity"] for item in equity_curve]) if equity_curve else 0.0
    win_rate = len(positive_returns) / len(cycle_returns) if cycle_returns else 0.0
    profit_loss_ratio = (
        abs(sum(positive_returns) / len(positive_returns)) / abs(sum(negative_returns) / len(negative_returns))
        if positive_returns and negative_returns
        else None
    )

    summary = {
        "cumulative_return_pct": round(cumulative_return * 100, 2),
        "annual_return_pct": round(annual_return * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "win_rate_pct": round(win_rate * 100, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 2) if profit_loss_ratio is not None else None,
        "trade_count": int(trade_count),
        "cycle_count": int(len(cycle_rows)),
        "avg_holding_days": avg_holding_days,
        "empty_cycles": int(empty_cycles),
    }

    if not trade_rows:
        warnings.append("当前参数下没有形成可成交的回测样本，系统已完成尝试，但这组条件暂时无法产出有效交易。")

    warnings.extend(_build_sample_guidance(config, summary, screen_payload))

    response = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "module": "backtest",
        "data_sources": ["Tushare daily", "Tushare daily_basic", "Tushare adj_factor", "Tushare cyq_perf (conditional)"],
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "history_years": config["history_years"],
            "trade_days": len(active_trade_dates),
            "evaluated_start_date": evaluated_start_dt.strftime("%Y-%m-%d"),
            "evaluated_end_date": evaluated_end_dt.strftime("%Y-%m-%d"),
            "evaluated_span_days": trade_span_days,
        },
        "strategy": {
            "screen_payload": screen_payload,
            "summary": _summarize_strategy(
                screen_payload,
                config["top_n"],
                config["holding_days"],
                config["history_years"],
                config["execution_mode"],
            ),
        },
        "execution": {
            "execution_mode": config["execution_mode"],
            "is_sampled_result": config["execution_mode"] != "full",
            "evaluation_scope": "sampled_recent_cycles" if config["execution_mode"] != "full" else "full_history_window",
            "adj_type": config["adj_type"],
            "top_n": config["top_n"],
            "holding_days": config["holding_days"],
            "rebalance_frequency_days": config["holding_days"],
            "buy_rule": "T 日收盘选股，T+1 开盘买入",
            "sell_rule": f"持有 {config['holding_days']} 天后卖出，若跌停或停牌则顺延至下一个可成交交易日",
            "constraints": constraints,
            "costs": {
                "buy_fee": costs.buy_fee,
                "sell_fee": costs.sell_fee,
                "sell_tax": costs.sell_tax,
                "slippage": costs.slippage,
            },
        },
        "summary": summary,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "yearly_returns": [{"year": year, "return_pct": round(value * 100, 2)} for year, value in sorted(yearly_return_map.items())],
        "cycle_samples": cycle_rows[-12:],
        "trade_samples": trade_rows[-20:],
        "warnings": warnings,
        "debug": {
            "average_candidates_per_cycle": round(total_candidates / max(len(selection_indices), 1), 2),
            "panel_rows": int(len(panel_df)),
            "used_cyq_fields": include_cyq,
            "selection_cycles_total": int(len(full_selection_indices)),
            "selection_cycles_used": int(len(selection_indices)),
            "required_trade_dates": int(len(required_trade_dates)),
            "hist_lookback_days": int(hist_lookback_days),
            "fetch_elapsed_ms": fetch_elapsed_ms,
            "compute_elapsed_ms": round((time.perf_counter() - compute_started_at) * 1000, 2),
            "total_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
        "sparkline": _build_ascii_curve([item["equity"] for item in equity_curve]),
    }

    saved_file = save_backtest_result(response)
    response["saved_file"] = saved_file
    return response


def save_backtest_result(result: dict[str, Any]) -> str:
    _ensure_dir(BACKTEST_RESULT_DIR)
    base_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = BACKTEST_RESULT_DIR / f"{base_name}.json"
    counter = 2
    while target.exists():
        target = BACKTEST_RESULT_DIR / f"{base_name}_{counter:02d}.json"
        counter += 1
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def list_saved_backtests(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_dir(BACKTEST_RESULT_DIR)
    files = sorted(BACKTEST_RESULT_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    history: list[dict[str, Any]] = []
    for path in files[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summary = payload.get("summary") or {}
        window = payload.get("window") or {}
        execution = payload.get("execution") or {}
        history.append(
            {
                "file_name": path.name,
                "file_path": str(path),
                "generated_at": payload.get("generated_at", ""),
                "history_years": window.get("history_years"),
                "holding_days": execution.get("holding_days"),
                "top_n": execution.get("top_n"),
                "execution_mode": execution.get("execution_mode"),
                "cumulative_return_pct": summary.get("cumulative_return_pct"),
                "max_drawdown_pct": summary.get("max_drawdown_pct"),
                "trade_count": summary.get("trade_count"),
            }
        )
    return history
