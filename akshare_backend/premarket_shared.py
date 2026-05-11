from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


class PayloadValidationError(ValueError):
    """Raised when the request payload does not satisfy the screener contract."""


FILTER_CAPABILITY = [
    {"id": "price_range", "label": "股价区间", "status": "supported_now", "source": "tushare_daily", "field": "latest_price"},
    {"id": "total_market_cap", "label": "总市值区间", "status": "supported_now", "source": "tushare_daily_basic", "field": "total_market_cap"},
    {"id": "circulating_market_cap", "label": "流通市值区间", "status": "supported_now", "source": "tushare_daily_basic", "field": "circulating_market_cap"},
    {"id": "change_pct", "label": "涨跌幅区间", "status": "supported_now", "source": "tushare_daily", "field": "change_pct"},
    {"id": "turnover_rate", "label": "换手率区间", "status": "supported_now", "source": "tushare_daily_basic", "field": "turnover_rate"},
    {"id": "amount", "label": "成交额区间", "status": "supported_now", "source": "tushare_daily", "field": "amount"},
    {"id": "volume_ratio", "label": "量比区间", "status": "supported_now", "source": "tushare_daily_basic", "field": "volume_ratio"},
    {"id": "amplitude", "label": "振幅区间", "status": "supported_now", "source": "tushare_daily", "field": "amplitude"},
    {"id": "rise_n_days", "label": "近 N 日涨幅", "status": "requires_hist", "source": "tushare_daily_history", "field": "rise_n_days"},
    {"id": "pullback_n_days", "label": "近 N 日回撤", "status": "requires_hist", "source": "tushare_daily_history", "field": "pullback_n_days"},
    {"id": "ma_position", "label": "均线位置", "status": "requires_hist", "source": "tushare_daily_history", "field": "ma_position"},
    {"id": "ma_breakout", "label": "均线突破", "status": "requires_hist", "source": "tushare_daily_history", "field": "ma_breakout"},
    {"id": "new_high_low", "label": "N 日新高 / 新低", "status": "requires_hist", "source": "tushare_daily_history", "field": "new_high_low"},
    {"id": "consecutive_up_down", "label": "连续涨跌天数", "status": "requires_hist", "source": "tushare_daily_history", "field": "consecutive_up_down"},
    {"id": "volume_expansion_shrink", "label": "持续放量 / 缩量", "status": "requires_hist", "source": "tushare_daily_history", "field": "volume_expansion_shrink"},
    {"id": "sector_or_concept", "label": "行业 / 概念", "status": "requires_extra_source", "source": "future_tushare_concept", "field": "industry"},
    {"id": "chip_concentration", "label": "筹码集中度", "status": "supported_now", "source": "tushare_cyq_perf", "field": "chip_concentration"},
    {"id": "winner_rate", "label": "获利盘比例", "status": "supported_now", "source": "tushare_cyq_perf", "field": "winner_rate"},
    {"id": "price_vs_chip", "label": "现价相对筹码成本", "status": "supported_now", "source": "tushare_cyq_perf", "field": "price_vs_chip"},
    {"id": "paused_stock", "label": "停牌过滤", "status": "supported_by_rule", "source": "tushare_daily", "field": "amount"},
    {"id": "st_filter", "label": "ST 过滤", "status": "supported_by_rule", "source": "tushare_stock_basic", "field": "name"},
    {"id": "market_scope", "label": "市场范围", "status": "supported_by_rule", "source": "tushare_stock_basic", "field": "symbol"},
    {"id": "new_listing_90d", "label": "90 天内新股过滤", "status": "supported_by_rule", "source": "tushare_stock_basic", "field": "listing_days"},
]

DEFAULT_PAYLOAD = {
    "mode": "pre",
    "screen_depth": "fast",
    "market_scope": "沪深主板 + 创业板",
    "exclude_st": True,
    "exclude_paused": True,
    "exclude_bse": True,
    "exclude_new_listing_90d": True,
    "filters": {
        "price_range": None,
        "total_market_cap": None,
        "circulating_market_cap": None,
        "change_pct": None,
        "turnover_rate": None,
        "amount": None,
        "amplitude": None,
        "volume_ratio": None,
        "rise_n_days": None,
        "pullback_n_days": None,
        "volume_expansion_shrink": None,
        "ma_position": None,
        "ma_breakout": None,
        "new_high_low": None,
        "consecutive_up_down": None,
        "sector_or_concept": None,
        "chip_concentration": None,
        "winner_rate": None,
        "price_vs_chip": None,
    },
}

RESULT_DIR = Path(__file__).resolve().parent.parent / "result"

SUPPORTED_HIST_FILTERS = {
    "rise_n_days",
    "pullback_n_days",
    "ma_position",
    "ma_breakout",
    "new_high_low",
    "consecutive_up_down",
    "volume_expansion_shrink",
}

SUPPORTED_MODES = {"pre", "post"}
SUPPORTED_SCREEN_DEPTHS = {"fast", "full"}
SUPPORTED_MA_POSITION = {"", None, "above_ma5_ma10", "near_ma20"}
SUPPORTED_MA_BREAKOUT = {"", None, "breakout_ma20", "breakout_ma60"}
SUPPORTED_NEW_HIGH_LOW = {"", None, "high_20d", "high_60d", "low_20d"}
SUPPORTED_VOLUME_RULE = {"", None, "volume_expand_2d", "volume_shrink_2d"}


def build_capability_report() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "filters": FILTER_CAPABILITY,
    }


def ensure_numeric(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or value is None:
        raise PayloadValidationError(f"{field_name} 不能为空。")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PayloadValidationError(f"{field_name} 必须为数字。") from exc


def validate_range_filter(name: str, bounds: Any, allow_negative: bool = False) -> list[float] | None:
    if bounds in (None, "", []):
        return None
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise PayloadValidationError(f"{name} 必须提供两个边界值。")

    lower = ensure_numeric(bounds[0], f"{name} 下限")
    upper = ensure_numeric(bounds[1], f"{name} 上限")
    if not allow_negative and (lower < 0 or upper < 0):
        raise PayloadValidationError(f"{name} 不能为负数。")
    if lower > upper:
        raise PayloadValidationError(f"{name} 下限不能大于上限。")
    return [lower, upper]


def validate_day_range_filter(name: str, value: Any, allow_negative_bounds: bool = False) -> dict[str, Any] | None:
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise PayloadValidationError(f"{name} 必须为结构化对象。")

    days = int(ensure_numeric(value.get("days"), f"{name} 天数"))
    bounds = validate_range_filter(name, value.get("bounds"), allow_negative=allow_negative_bounds)
    if days <= 0:
        raise PayloadValidationError(f"{name} 天数必须大于 0。")
    if bounds is None:
        raise PayloadValidationError(f"{name} 必须提供区间范围。")
    return {"days": days, "bounds": bounds}


def validate_consecutive_filter(value: Any) -> dict[str, Any] | None:
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise PayloadValidationError("连续涨跌条件必须为结构化对象。")

    direction = value.get("direction")
    if direction not in {"up", "down"}:
        raise PayloadValidationError("连续涨跌方向只能为 up 或 down。")

    min_days = int(ensure_numeric(value.get("min_days"), "连续涨跌最小天数"))
    max_days = int(ensure_numeric(value.get("max_days"), "连续涨跌最大天数"))
    if min_days <= 0 or max_days <= 0:
        raise PayloadValidationError("连续涨跌天数必须大于 0。")
    if min_days > max_days:
        raise PayloadValidationError("连续涨跌最小天数不能大于最大天数。")
    return {"direction": direction, "min_days": min_days, "max_days": max_days}


def normalize_market_scope(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return DEFAULT_PAYLOAD["market_scope"]
    if "科创" in text or "绉戝垱" in text:
        return "科创板"
    if "主板" in text and "创业" not in text and "鍒涗笟" not in text:
        return "沪深主板"
    return "沪深主板 + 创业板"


def normalize_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {
        "mode": DEFAULT_PAYLOAD["mode"],
        "screen_depth": DEFAULT_PAYLOAD["screen_depth"],
        "market_scope": DEFAULT_PAYLOAD["market_scope"],
        "exclude_st": DEFAULT_PAYLOAD["exclude_st"],
        "exclude_paused": DEFAULT_PAYLOAD["exclude_paused"],
        "exclude_bse": DEFAULT_PAYLOAD["exclude_bse"],
        "exclude_new_listing_90d": DEFAULT_PAYLOAD["exclude_new_listing_90d"],
        "filters": DEFAULT_PAYLOAD["filters"].copy(),
    }
    if not payload:
        payload = {}

    for key in ("mode", "screen_depth", "market_scope", "exclude_st", "exclude_paused", "exclude_bse", "exclude_new_listing_90d"):
        if key in payload:
            merged[key] = payload[key]
    merged["filters"].update(payload.get("filters", {}))
    return validate_payload(merged)


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mode") not in SUPPORTED_MODES:
        raise PayloadValidationError("mode 只能为 pre 或 post。")
    if payload.get("screen_depth") not in SUPPORTED_SCREEN_DEPTHS:
        raise PayloadValidationError("screen_depth 只能为 fast 或 full。")

    payload["market_scope"] = normalize_market_scope(payload.get("market_scope"))

    for key in ("exclude_st", "exclude_paused", "exclude_bse", "exclude_new_listing_90d"):
        payload[key] = bool(payload.get(key, False))

    filters = payload.get("filters", {})
    filters["price_range"] = validate_range_filter("股价区间", filters.get("price_range"))
    filters["total_market_cap"] = validate_range_filter("总市值区间", filters.get("total_market_cap"))
    filters["circulating_market_cap"] = validate_range_filter("流通市值区间", filters.get("circulating_market_cap"))
    filters["change_pct"] = validate_range_filter("涨跌幅区间", filters.get("change_pct"), allow_negative=True)
    filters["turnover_rate"] = validate_range_filter("换手率区间", filters.get("turnover_rate"))
    filters["amount"] = validate_range_filter("成交额区间", filters.get("amount"))
    filters["amplitude"] = validate_range_filter("振幅区间", filters.get("amplitude"))
    filters["volume_ratio"] = validate_range_filter("量比区间", filters.get("volume_ratio"))
    filters["chip_concentration"] = validate_range_filter("筹码集中度", filters.get("chip_concentration"))
    filters["winner_rate"] = validate_range_filter("获利盘比例", filters.get("winner_rate"))
    filters["price_vs_chip"] = validate_range_filter("现价相对筹码成本", filters.get("price_vs_chip"), allow_negative=True)

    if payload["screen_depth"] == "full":
        filters["rise_n_days"] = validate_day_range_filter("近 N 日涨幅", filters.get("rise_n_days"), allow_negative_bounds=True)
        filters["pullback_n_days"] = validate_day_range_filter("近 N 日回撤", filters.get("pullback_n_days"))
        filters["consecutive_up_down"] = validate_consecutive_filter(filters.get("consecutive_up_down"))
        if filters.get("ma_position") not in SUPPORTED_MA_POSITION:
            raise PayloadValidationError("均线位置条件不在支持范围内。")
        if filters.get("ma_breakout") not in SUPPORTED_MA_BREAKOUT:
            raise PayloadValidationError("均线突破条件不在支持范围内。")
        if filters.get("new_high_low") not in SUPPORTED_NEW_HIGH_LOW:
            raise PayloadValidationError("新高新低条件不在支持范围内。")
        if filters.get("volume_expansion_shrink") not in SUPPORTED_VOLUME_RULE:
            raise PayloadValidationError("放量缩量条件不在支持范围内。")
    else:
        for key in ("rise_n_days", "pullback_n_days", "consecutive_up_down", "ma_position", "ma_breakout", "new_high_low", "volume_expansion_shrink"):
            filters[key] = None
        payload["exclude_new_listing_90d"] = False

    filters["sector_or_concept"] = None
    payload["filters"] = filters
    return payload


def infer_market(symbol: str) -> str:
    symbol = str(symbol)
    if symbol.startswith(("688", "689")):
        return "科创板"
    if symbol.startswith(("300", "301")):
        return "创业板"
    if symbol.startswith(("600", "601", "603", "605")):
        return "沪主板"
    if symbol.startswith(("000", "001", "002", "003")):
        return "深主板"
    if symbol.startswith(("4", "8", "92")):
        return "北交所"
    return "其他"


def apply_market_scope(df: pd.DataFrame, market_scope: str) -> pd.DataFrame:
    if market_scope == "沪深主板":
        return df[df["market"].isin(["沪主板", "深主板"])]
    if market_scope == "科创板":
        return df[df["market"] == "科创板"]
    return df[df["market"].isin(["沪主板", "深主板", "创业板"])]


def apply_range_filter(df: pd.DataFrame, column: str, bounds: list[float] | None) -> pd.DataFrame:
    if column not in df.columns or bounds is None:
        return df
    lower, upper = bounds
    return df[df[column].between(lower, upper, inclusive="both")]


def needs_hist_enrichment(payload: dict[str, Any]) -> bool:
    if payload.get("screen_depth", "fast") != "full":
        return False
    if payload.get("exclude_new_listing_90d", False):
        return True
    filters = payload.get("filters", {})
    return any(filters.get(key) not in (None, "", {}, []) for key in SUPPORTED_HIST_FILTERS)


def format_amount_yi(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value / 1e8:.1f} 亿元"


def label_strength(value: float, strong_threshold: float, medium_threshold: float) -> str:
    if pd.isna(value):
        return "待补"
    if value >= strong_threshold:
        return "强"
    if value >= medium_threshold:
        return "中"
    return "弱"


def priority_from_score(score: float) -> tuple[str, str]:
    if score >= 85:
        return "高优先级", "high"
    if score >= 70:
        return "中优先级", "mid"
    return "低优先级", "low"


def build_first_summary(row: pd.Series) -> str:
    return f"价格 {row['latest_price']:.2f} 元、成交额 {format_amount_yi(row['amount'])}、换手率 {row['turnover_rate']:.1f}% 命中首轮条件。"


def build_reason(row: pd.Series, mode: str) -> str:
    industry = row.get("industry", "待补行业")
    if mode == "post":
        return f"当日涨跌幅 {row['change_pct']:.1f}% 、换手率 {row['turnover_rate']:.1f}% ，资金活跃度较高，适合纳入盘后复盘候选。行业归属：{industry}。"
    return f"60 日趋势 {row.get('change_pct_60d', 0):.1f}% 、量比 {row['volume_ratio']:.1f} ，具备较好的盘前关注价值。行业归属：{industry}。"


def build_risk(row: pd.Series) -> str:
    if row["amplitude"] >= 10:
        return "振幅偏大，短线波动风险较高。"
    if row["turnover_rate"] >= 15:
        return "换手率偏高，需要留意冲高后的分歧。"
    return "当前风险可控，但仍需结合板块承接观察。"


def build_metrics(row: pd.Series) -> list[str]:
    metrics = [
        f"股价 {row['latest_price']:.2f} 元",
        f"换手率 {row['turnover_rate']:.1f}%",
        f"成交额 {format_amount_yi(row['amount'])}",
        f"60 日涨幅 {row.get('change_pct_60d', 0):.1f}%",
    ]
    if "rise_n_pct" in row and not pd.isna(row["rise_n_pct"]):
        metrics.append(f"近 {int(row.get('rise_n_days_value', 5))} 日涨幅 {row['rise_n_pct']:.1f}%")
    if "pullback_n_pct" in row and not pd.isna(row["pullback_n_pct"]):
        metrics.append(f"近 {int(row.get('pullback_n_days_value', 10))} 日回撤 {row['pullback_n_pct']:.1f}%")
    return metrics


def build_dimension_summary(row: pd.Series) -> dict[str, str]:
    trend_flag = "待补"
    if "breakout_ma20" in row and bool(row["breakout_ma20"]):
        trend_flag = "强"
    elif "close_above_ma5_ma10" in row and bool(row["close_above_ma5_ma10"]):
        trend_flag = "中"

    return {
        "题材与催化": str(row.get("industry", "待接行业映射")),
        "资金与情绪": label_strength(row["turnover_rate"], 10, 5),
        "市场地位": label_strength(row["total_market_cap"], 1.2e11, 4e10),
        "趋势增强": trend_flag,
    }


def build_frontend_rows(df: pd.DataFrame, mode: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in df.head(10).iterrows():
        priority_label, priority_class = priority_from_score(float(row["score"]))
        rows.append(
            {
                "rank": int(row["rank"]),
                "score": int(row["score"]),
                "priority": priority_label,
                "priorityClass": priority_class,
                "code": row["symbol"],
                "name": row["name"],
                "market": row["market"],
                "sectors": str(row.get("industry", "待接行业 / 概念映射")),
                "first": build_first_summary(row),
                "reason": build_reason(row, mode),
                "risk": build_risk(row),
                "metrics": build_metrics(row),
                "dimensions": build_dimension_summary(row),
            }
        )
    return rows


def build_result_filename() -> Path:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    base_name = datetime.now().strftime("%Y-%m-%d_%H-%M")
    target = RESULT_DIR / f"{base_name}.xlsx"
    if not target.exists():
        return target

    suffix = 2
    while True:
        candidate = RESULT_DIR / f"{base_name}_{suffix:02d}.xlsx"
        if not candidate.exists():
            return candidate
        suffix += 1


def save_screen_result(df: pd.DataFrame, payload: dict[str, Any], mode: str) -> str:
    export_df = df.copy()
    if export_df.empty:
        export_df = pd.DataFrame(columns=["symbol", "name", "market", "score", "rank"])

    if "symbol" in export_df.columns:
        export_df["symbol"] = export_df["symbol"].astype(str).str.zfill(6)

    export_df.insert(0, "screen_mode", mode)
    export_df.insert(1, "screen_depth", payload.get("screen_depth", "fast"))
    export_df.insert(2, "market_scope", payload.get("market_scope", DEFAULT_PAYLOAD["market_scope"]))
    export_df.insert(3, "exported_at", datetime.now().isoformat(timespec="seconds"))

    file_path = build_result_filename()
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="screen_results")
        worksheet = writer.sheets["screen_results"]
        if "symbol" in export_df.columns:
            symbol_column_index = export_df.columns.get_loc("symbol") + 1
            for row_index in range(2, len(export_df) + 2):
                cell = worksheet.cell(row=row_index, column=symbol_column_index)
                cell.number_format = "@"
                cell.value = str(cell.value).zfill(6)
    return str(file_path)


def list_saved_results(limit: int = 20) -> list[dict[str, Any]]:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    items = sorted(RESULT_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
    history: list[dict[str, Any]] = []
    for path in items[:limit]:
        try:
            header_df = pd.read_excel(path, sheet_name="screen_results", nrows=1, dtype={"symbol": str})
        except Exception:
            header_df = pd.DataFrame()

        first_row = header_df.iloc[0].to_dict() if not header_df.empty else {}
        mode = str(first_row.get("screen_mode", "pre"))
        screen_depth = str(first_row.get("screen_depth", "fast"))
        scope = str(first_row.get("market_scope", DEFAULT_PAYLOAD["market_scope"]))
        exported_at = first_row.get("exported_at")
        if isinstance(exported_at, pd.Timestamp):
            exported_text = exported_at.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")
        else:
            exported_text = str(exported_at or datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"))

        history.append(
            {
                "file_name": path.name,
                "file_path": str(path),
                "generated_at": exported_text,
                "mode": mode,
                "mode_label": "盘后复盘" if mode == "post" else "盘前预判",
                "screen_depth": screen_depth,
                "scope": scope,
            }
        )
    return history
