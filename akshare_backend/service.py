from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import akshare as ak
import pandas as pd


class PayloadValidationError(ValueError):
    """Raised when the request payload does not satisfy the screener contract."""


SPOT_RENAME_MAP = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "latest_price",
    "涨跌幅": "change_pct",
    "涨跌额": "change_amount",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "最高": "high_price",
    "最低": "low_price",
    "今开": "open_price",
    "昨收": "prev_close",
    "量比": "volume_ratio",
    "换手率": "turnover_rate",
    "市盈率-动态": "pe_dynamic",
    "市净率": "pb_ratio",
    "总市值": "total_market_cap",
    "流通市值": "circulating_market_cap",
    "涨速": "speed",
    "5分钟涨跌": "change_5m",
    "60日涨跌幅": "change_pct_60d",
    "年初至今涨跌幅": "change_pct_ytd",
}

FILTER_CAPABILITY = [
    {"id": "price_range", "label": "股价区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "latest_price"},
    {"id": "total_market_cap", "label": "总市值区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "total_market_cap"},
    {"id": "circulating_market_cap", "label": "流通市值区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "circulating_market_cap"},
    {"id": "change_pct", "label": "涨跌幅区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "change_pct"},
    {"id": "turnover_rate", "label": "换手率区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "turnover_rate"},
    {"id": "amount", "label": "成交额区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "amount"},
    {"id": "volume_ratio", "label": "量比区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "volume_ratio"},
    {"id": "amplitude", "label": "振幅区间", "status": "supported_now", "source": "stock_zh_a_spot_em", "field": "amplitude"},
    {"id": "rise_n_days", "label": "近 N 日涨幅", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "rise_n_days"},
    {"id": "pullback_n_days", "label": "近 N 日回撤", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "pullback_n_days"},
    {"id": "ma_position", "label": "均线位置", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "ma_position"},
    {"id": "ma_breakout", "label": "均线突破", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "ma_breakout"},
    {"id": "new_high_low", "label": "N 日新高 / 新低", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "new_high_low"},
    {"id": "consecutive_up_down", "label": "连续涨跌天数", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "consecutive_up_down"},
    {"id": "volume_expansion_shrink", "label": "持续放量 / 缩量", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "volume_expansion_shrink"},
    {"id": "sector_or_concept", "label": "行业 / 概念", "status": "requires_extra_source", "source": "concept mapping", "field": "sectors"},
    {"id": "chip_concentration", "label": "筹码集中度", "status": "unsupported_currently", "source": "not in MVP", "field": None},
    {"id": "paused_stock", "label": "停牌过滤", "status": "supported_by_rule", "source": "stock_zh_a_spot_em", "field": "amount"},
    {"id": "st_filter", "label": "ST 过滤", "status": "supported_by_rule", "source": "stock_zh_a_spot_em", "field": "name"},
    {"id": "market_scope", "label": "市场范围", "status": "supported_by_rule", "source": "stock_zh_a_spot_em", "field": "symbol"},
    {"id": "new_listing_90d", "label": "90 天内新股过滤", "status": "requires_hist", "source": "stock_zh_a_hist", "field": "listing_days"},
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
        "price_range": [8, 35],
        "total_market_cap": [6e9, 4.5e10],
        "circulating_market_cap": [4e9, 3e10],
        "change_pct": [-2, 6],
        "turnover_rate": [3, 18],
        "amount": [2e8, 8e9],
        "amplitude": [2, 12],
        "volume_ratio": [1.2, 3.8],
        "rise_n_days": {"days": 5, "bounds": [3, 18]},
        "pullback_n_days": {"days": 10, "bounds": [0, 12]},
        "volume_expansion_shrink": "volume_expand_2d",
        "ma_position": "above_ma5_ma10",
        "ma_breakout": "breakout_ma20",
        "new_high_low": "high_20d",
        "consecutive_up_down": {"direction": "up", "min_days": 2, "max_days": 4},
        "sector_or_concept": None,
        "chip_concentration": None,
    },
}

SPOT_CACHE_TTL_SECONDS = 180
HIST_CACHE_TTL_SECONDS = 900
NEWS_CACHE_TTL_SECONDS = 600
MAX_HIST_CANDIDATES = 40
RESULT_DIR = Path(__file__).resolve().parent.parent / "result"
SPOT_CACHE: dict[str, Any] = {"expires_at": 0.0, "data": None}
HIST_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
NEWS_CACHE: dict[str, Any] = {"expires_at": 0.0, "brief_date": None, "data": None}

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
SUPPORTED_MARKET_SCOPES = {"沪深主板 + 创业板", "沪深主板", "科创板"}
SUPPORTED_MA_POSITION = {"", None, "above_ma5_ma10", "near_ma20"}
SUPPORTED_MA_BREAKOUT = {"", None, "breakout_ma20", "breakout_ma60"}
SUPPORTED_NEW_HIGH_LOW = {"", None, "high_20d", "high_60d", "low_20d"}
SUPPORTED_VOLUME_RULE = {"", None, "volume_expand_2d", "volume_shrink_2d"}


def build_capability_report() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "filters": FILTER_CAPABILITY,
    }


def format_datetime_text(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def split_breakfast_summary(summary: str) -> list[str]:
    text = re.sub(r"^【[^】]+】", "", str(summary or "")).strip()
    if not text:
        return []

    parts = [item.strip("；;。 ") for item in re.split(r"\d+、", text) if item.strip()]
    return [item for item in parts if item]


def build_brief_item(title: str, summary: str, published_at: str, source: str, url: str | None = None) -> dict[str, str]:
    item = {
        "title": str(title or "").strip(),
        "summary": str(summary or "").strip(),
        "published_at": str(published_at or "").strip(),
        "source": source,
    }
    if url:
        item["url"] = url
    return item


def fetch_cls_focus_brief(today_text: str) -> dict[str, Any] | None:
    cls_df = ak.stock_info_global_cls(symbol="重点")
    if cls_df.empty:
        return None

    working_df = cls_df.copy()
    working_df["发布日期"] = working_df["发布日期"].astype(str)
    working_df["发布时间"] = working_df["发布时间"].astype(str)
    today_df = working_df[working_df["发布日期"] == today_text].copy()
    if today_df.empty:
        return None

    today_df["_sort_key"] = pd.to_datetime(
        today_df["发布日期"] + " " + today_df["发布时间"],
        errors="coerce",
    )
    today_df = today_df.sort_values("_sort_key", ascending=False).head(6)

    items = [
        build_brief_item(
            title=row["标题"],
            summary=row["内容"],
            published_at=f"{row['发布日期']} {row['发布时间']}",
            source="财联社重点电报",
        )
        for _, row in today_df.iterrows()
    ]
    if not items:
        return None

    return {
        "status": "ok",
        "brief_date": today_text,
        "source": "stock_info_global_cls",
        "source_label": "财联社重点电报",
        "updated_at": items[0]["published_at"],
        "items": items,
    }


def fetch_eastmoney_breakfast_brief() -> dict[str, Any] | None:
    breakfast_df = ak.stock_info_cjzc_em()
    if breakfast_df.empty:
        return None

    latest_row = breakfast_df.iloc[0].to_dict()
    bullets = split_breakfast_summary(str(latest_row.get("摘要", "")))
    if not bullets:
        bullets = [str(latest_row.get("摘要", "")).strip()]

    items = [
        build_brief_item(
            title=f"财经早餐要点 {index}",
            summary=bullet,
            published_at=format_datetime_text(latest_row.get("发布时间")),
            source="东方财富财经早餐",
            url=str(latest_row.get("链接", "")).strip() or None,
        )
        for index, bullet in enumerate(bullets[:6], start=1)
        if bullet
    ]
    if not items:
        return None

    brief_date = items[0]["published_at"][:10] if items[0]["published_at"] else datetime.now().strftime("%Y-%m-%d")
    return {
        "status": "degraded",
        "brief_date": brief_date,
        "source": "stock_info_cjzc_em",
        "source_label": "东方财富财经早餐",
        "updated_at": items[0]["published_at"],
        "items": items,
    }


def get_market_news_brief(force_refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    today_text = datetime.now().strftime("%Y-%m-%d")
    if (
        not force_refresh
        and NEWS_CACHE["data"] is not None
        and NEWS_CACHE["brief_date"] == today_text
        and now < NEWS_CACHE["expires_at"]
    ):
        return NEWS_CACHE["data"]

    errors: list[str] = []
    brief: dict[str, Any] | None = None

    try:
        brief = fetch_cls_focus_brief(today_text)
    except Exception as exc:  # pragma: no cover
        errors.append(f"stock_info_global_cls: {exc}")

    if brief is None:
        try:
            brief = fetch_eastmoney_breakfast_brief()
        except Exception as exc:  # pragma: no cover
            errors.append(f"stock_info_cjzc_em: {exc}")

    if brief is None:
        brief = {
            "status": "error",
            "brief_date": today_text,
            "source": "unavailable",
            "source_label": "新闻接口暂不可用",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": [
                build_brief_item(
                    title="新闻简报暂不可用",
                    summary="AKShare 新闻源本轮未成功返回数据，页面保留筛选功能，稍后可再次刷新简报。",
                    published_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    source="fallback",
                )
            ],
        }

    brief["generated_at"] = datetime.now().isoformat(timespec="seconds")
    brief["errors"] = errors

    NEWS_CACHE.update(
        {
            "expires_at": now + NEWS_CACHE_TTL_SECONDS,
            "brief_date": today_text,
            "data": brief,
        }
    )
    return brief


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
    if payload.get("market_scope") not in SUPPORTED_MARKET_SCOPES:
        raise PayloadValidationError("market_scope 不在支持范围内。")

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
    filters["chip_concentration"] = None
    payload["filters"] = filters
    return payload


def fetch_spot_snapshot(force_refresh: bool = False) -> pd.DataFrame:
    now = time.time()
    if not force_refresh and SPOT_CACHE["data"] is not None and now < SPOT_CACHE["expires_at"]:
        return SPOT_CACHE["data"].copy()

    raw_df = ak.stock_zh_a_spot_em()
    df = raw_df.rename(columns=SPOT_RENAME_MAP).copy()
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)

    numeric_columns = [
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
        "speed",
        "change_5m",
        "change_pct_60d",
        "change_pct_ytd",
    ]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["market"] = df["symbol"].map(infer_market)
    df["is_st"] = df["name"].fillna("").str.contains("ST", case=False, regex=False)
    df["is_bse"] = df["symbol"].str.startswith(("4", "8", "92"))

    SPOT_CACHE["data"] = df.copy()
    SPOT_CACHE["expires_at"] = now + SPOT_CACHE_TTL_SECONDS
    return df


def infer_market(symbol: str) -> str:
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
    return working_df


def needs_hist_enrichment(payload: dict[str, Any]) -> bool:
    if payload.get("screen_depth", "fast") != "full":
        return False
    if payload.get("exclude_new_listing_90d", False):
        return True
    filters = payload.get("filters", {})
    return any(filters.get(key) not in (None, "", {}, []) for key in SUPPORTED_HIST_FILTERS)


def select_hist_candidates(df: pd.DataFrame, limit: int = MAX_HIST_CANDIDATES) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    sort_columns = ["amount", "turnover_rate", "volume_ratio", "change_pct_60d"]
    return df.sort_values(sort_columns, ascending=[False, False, False, False]).head(limit).copy()


def fetch_hist_df(symbol: str) -> pd.DataFrame | None:
    now = time.time()
    cached = HIST_CACHE.get(symbol)
    if cached and now < cached[0]:
        return cached[1].copy()

    try:
        hist_df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date="20240101",
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq",
        )
    except Exception:
        return None

    if hist_df is None or hist_df.empty:
        return None

    hist_df = hist_df.rename(
        columns={
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "涨跌幅": "change_pct",
        }
    ).copy()

    for column in ("open", "close", "high", "low", "volume", "change_pct"):
        if column in hist_df.columns:
            hist_df[column] = pd.to_numeric(hist_df[column], errors="coerce")

    hist_df["trade_date"] = pd.to_datetime(hist_df["trade_date"], errors="coerce")
    hist_df = hist_df.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
    if hist_df.empty:
        return None

    HIST_CACHE[symbol] = (now + HIST_CACHE_TTL_SECONDS, hist_df.copy())
    return hist_df


def safe_pct_change(current: float, previous: float) -> float:
    if previous in (None, 0) or pd.isna(previous):
        return float("nan")
    return (current / previous - 1) * 100


def count_consecutive(changes: list[float], positive: bool) -> int:
    count = 0
    for value in reversed(changes):
        if positive and value > 0:
            count += 1
        elif not positive and value < 0:
            count += 1
        else:
            break
    return count


def count_volume_trend(volumes: list[float], increasing: bool) -> int:
    if len(volumes) < 2:
        return 0
    count = 0
    for index in range(len(volumes) - 1, 0, -1):
        current = volumes[index]
        previous = volumes[index - 1]
        if increasing and current > previous:
            count += 1
        elif not increasing and current < previous:
            count += 1
        else:
            break
    return count


def compute_hist_features(symbol: str) -> dict[str, Any] | None:
    hist_df = fetch_hist_df(symbol)
    if hist_df is None or len(hist_df) < 20:
        return None

    latest = hist_df.iloc[-1]
    close = float(latest["close"])
    volume = float(latest["volume"]) if not pd.isna(latest["volume"]) else float("nan")

    ma5 = hist_df["close"].tail(5).mean()
    ma10 = hist_df["close"].tail(10).mean()
    ma20 = hist_df["close"].tail(20).mean()
    ma60 = hist_df["close"].tail(min(60, len(hist_df))).mean()

    rise_5d = safe_pct_change(close, hist_df["close"].iloc[-6]) if len(hist_df) >= 6 else float("nan")
    high_10d = hist_df["high"].tail(10).max() if "high" in hist_df.columns else float("nan")
    pullback_10d = safe_pct_change(high_10d, close) if not pd.isna(high_10d) else float("nan")
    high_20d = hist_df["high"].tail(20).max()
    high_60d = hist_df["high"].tail(min(60, len(hist_df))).max()
    low_20d = hist_df["low"].tail(20).min()

    changes = hist_df["change_pct"].fillna(0).tail(10).tolist()
    volumes = hist_df["volume"].fillna(0).tail(10).tolist()

    return {
        "symbol": symbol,
        "rise_5d_pct": rise_5d,
        "pullback_10d_pct": pullback_10d,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "close_hist": close,
        "close_above_ma5_ma10": bool(close >= ma5 and close >= ma10),
        "close_near_ma20": bool(abs(close - ma20) / ma20 <= 0.03) if ma20 else False,
        "breakout_ma20": bool(close >= ma20 and hist_df["close"].iloc[-2] < hist_df["close"].tail(20).mean()) if len(hist_df) >= 21 else False,
        "breakout_ma60": bool(close >= ma60 and hist_df["close"].iloc[-2] < hist_df["close"].tail(min(60, len(hist_df) - 1)).mean()) if len(hist_df) >= 61 else False,
        "is_high_20d": bool(close >= high_20d),
        "is_high_60d": bool(close >= high_60d),
        "is_low_20d": bool(close <= low_20d),
        "consecutive_up_days": count_consecutive(changes, positive=True),
        "consecutive_down_days": count_consecutive(changes, positive=False),
        "volume_expand_days": count_volume_trend(volumes, increasing=True),
        "volume_shrink_days": count_volume_trend(volumes, increasing=False),
        "listing_days": int(len(hist_df)),
        "latest_hist_volume": volume,
    }


def enrich_candidates(df: pd.DataFrame, payload: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    info = {
        "applied": False,
        "candidate_count": 0,
        "success_count": 0,
        "failed_symbols": [],
        "applied_filters": [],
    }
    if df.empty or not needs_hist_enrichment(payload):
        return df.copy(), info

    candidates = select_hist_candidates(df)
    info["applied"] = True
    info["candidate_count"] = int(len(candidates))

    features: list[dict[str, Any]] = []
    failed_symbols: list[str] = []
    for symbol in candidates["symbol"].tolist():
        feature_row = compute_hist_features(symbol)
        if feature_row is None:
            failed_symbols.append(symbol)
            continue
        features.append(feature_row)

    info["success_count"] = len(features)
    info["failed_symbols"] = failed_symbols
    if not features:
        return candidates.copy(), info

    hist_df = pd.DataFrame(features)
    working_df = candidates.merge(hist_df, on="symbol", how="inner")
    working_df = apply_hist_filters(working_df, payload, info)
    return working_df, info


def apply_hist_filters(df: pd.DataFrame, payload: dict[str, Any], info: dict[str, Any]) -> pd.DataFrame:
    filters = payload.get("filters", {})
    working_df = df.copy()

    rise_n_days = filters.get("rise_n_days")
    if isinstance(rise_n_days, dict):
        working_df = apply_range_filter(working_df, "rise_5d_pct", rise_n_days["bounds"])
        info["applied_filters"].append("rise_n_days")

    pullback_n_days = filters.get("pullback_n_days")
    if isinstance(pullback_n_days, dict):
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

    if payload.get("exclude_new_listing_90d", False):
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
    trend_rank = working_df["change_pct_60d"].rank(pct=True)
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


def priority_from_score(score: float) -> tuple[str, str]:
    if score >= 85:
        return "高优先级", "high"
    if score >= 70:
        return "中优先级", "mid"
    return "低优先级", "low"


def format_amount_yi(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value / 1e8:.1f} 亿"


def label_strength(value: float, strong_threshold: float, medium_threshold: float) -> str:
    if pd.isna(value):
        return "待补"
    if value >= strong_threshold:
        return "强"
    if value >= medium_threshold:
        return "中"
    return "弱"


def build_reason(row: pd.Series, mode: str) -> str:
    if mode == "post":
        return (
            f"当日涨跌幅 {row['change_pct']:.1f}% 、换手率 {row['turnover_rate']:.1f}% ，"
            "资金活跃度较高，适合纳入盘后复盘候选。"
        )
    return (
        f"60 日趋势 {row['change_pct_60d']:.1f}% 、量比 {row['volume_ratio']:.1f} ，"
        "具备较好的盘前关注价值。"
    )


def build_risk(row: pd.Series) -> str:
    if row["amplitude"] >= 10:
        return "振幅偏大，短线波动风险较高。"
    if row["turnover_rate"] >= 15:
        return "换手率偏高，需要留意冲高后的分歧。"
    return "当前风险可控，但仍需结合板块承接观察。"


def build_first_summary(row: pd.Series) -> str:
    return f"价格 {row['latest_price']:.2f} 元、成交额 {format_amount_yi(row['amount'])}、换手率 {row['turnover_rate']:.1f}% 命中首轮条件。"


def build_metrics(row: pd.Series) -> list[str]:
    metrics = [
        f"股价 {row['latest_price']:.2f} 元",
        f"换手率 {row['turnover_rate']:.1f}%",
        f"成交额 {format_amount_yi(row['amount'])}",
        f"60 日涨幅 {row['change_pct_60d']:.1f}%",
    ]
    if "rise_5d_pct" in row and not pd.isna(row["rise_5d_pct"]):
        metrics.append(f"近 5 日涨幅 {row['rise_5d_pct']:.1f}%")
    if "pullback_10d_pct" in row and not pd.isna(row["pullback_10d_pct"]):
        metrics.append(f"近 10 日回撤 {row['pullback_10d_pct']:.1f}%")
    return metrics


def build_dimension_summary(row: pd.Series) -> dict[str, str]:
    trend_flag = "待补"
    if "breakout_ma20" in row and bool(row["breakout_ma20"]):
        trend_flag = "强"
    elif "close_above_ma5_ma10" in row and bool(row["close_above_ma5_ma10"]):
        trend_flag = "中"

    return {
        "题材与催化": "待接入映射",
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
                "sectors": "待接行业 / 概念映射",
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


def run_screen(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    merged_payload = normalize_payload(payload)
    mode = merged_payload.get("mode", "pre")
    spot_cache_hit = SPOT_CACHE["data"] is not None and time.time() < SPOT_CACHE["expires_at"]

    started_at = time.perf_counter()
    spot_df = fetch_spot_snapshot()
    fast_df = apply_fast_filters(spot_df, merged_payload)
    fast_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)

    enhance_started_at = time.perf_counter()
    enhanced_df, enhance_info = enrich_candidates(fast_df, merged_payload)
    enhance_elapsed_ms = round((time.perf_counter() - enhance_started_at) * 1000, 2)

    result_base_df = enhanced_df if enhance_info["applied"] and enhance_info["success_count"] > 0 else fast_df
    scored_df = score_candidates(result_base_df, mode)
    export_file = save_screen_result(scored_df, merged_payload, mode)

    return {
        "mode": mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_sources": ["AKShare stock_zh_a_spot_em", "AKShare stock_zh_a_hist (conditional)"],
        "unsupported_filters": [item for item in FILTER_CAPABILITY if item["status"] in {"requires_extra_source", "unsupported_currently"}],
        "market_scope": merged_payload["market_scope"],
        "screen_depth": merged_payload["screen_depth"],
        "first_round_count": int(len(fast_df)),
        "enhanced_count": int(len(enhanced_df)) if enhance_info["applied"] else int(len(fast_df)),
        "final_result_count": int(min(len(scored_df), 10)),
        "stage_meta": {
            "fast_filter_ms": fast_elapsed_ms,
            "enhancement_ms": enhance_elapsed_ms,
            "spot_cache_hit": spot_cache_hit,
            "hist_enhancement": enhance_info,
        },
        "export_file": export_file,
        "applied_payload": merged_payload,
        "results": build_frontend_rows(scored_df, mode),
    }


def probe_snapshot() -> dict[str, Any]:
    df = fetch_spot_snapshot()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": int(len(df)),
        "columns": list(df.columns),
        "sample": df.head(1).to_dict(orient="records"),
    }
