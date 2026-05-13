from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import pandas as pd


class TushareConfigError(RuntimeError):
    """Raised when the local Tushare token is missing."""


@dataclass(slots=True)
class TushareProbeResult:
    dataset: str
    ok: bool
    rows: int
    columns: list[str]
    detail: str = ""


def get_tushare_token() -> str:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise TushareConfigError("Missing TUSHARE_TOKEN environment variable.")
    return token


def get_tushare_http_url() -> str:
    return os.getenv("TUSHARE_HTTP_URL", "").strip()


def _ensure_tushare_no_proxy(http_url: str) -> None:
    if not http_url:
        return

    parsed = urlparse(http_url)
    host = (parsed.hostname or "").strip()
    if not host:
        return

    no_proxy_values = []
    for key in ("NO_PROXY", "no_proxy"):
        raw = os.getenv(key, "").strip()
        if raw:
            no_proxy_values.extend([item.strip() for item in raw.split(",") if item.strip()])

    required_hosts = {host, "127.0.0.1", "localhost"}
    merged = []
    seen = set()
    for item in [*no_proxy_values, *required_hosts]:
        if item not in seen:
            seen.add(item)
            merged.append(item)

    joined = ",".join(merged)
    os.environ["NO_PROXY"] = joined
    os.environ["no_proxy"] = joined


def get_tushare_client():
    import tushare as ts

    try:
        from .tushare_runtime_local import create_tushare_client
    except ImportError:
        try:
            from tushare_runtime_local import create_tushare_client
        except ImportError:
            create_tushare_client = None

    if create_tushare_client is not None:
        return create_tushare_client()

    token = get_tushare_token()
    ts.set_token(token)
    pro = ts.pro_api(token)
    http_url = get_tushare_http_url()
    if http_url:
        _ensure_tushare_no_proxy(http_url)
        pro._DataApi__http_url = http_url
    return pro


def get_recent_trade_date_text() -> str:
    now = datetime.now()
    end_date = now.strftime("%Y%m%d")
    start_date = (now - timedelta(days=30)).strftime("%Y%m%d")

    try:
        pro = get_tushare_client()
        calendar_df = pro.trade_cal(
            exchange="SSE",
            start_date=start_date,
            end_date=end_date,
            is_open="1",
        )
        if calendar_df is not None and not calendar_df.empty:
            calendar_df = calendar_df.sort_values("cal_date", ascending=True).reset_index(drop=True)
            trade_dates = calendar_df["cal_date"].astype(str).tolist()
            if not trade_dates:
                raise ValueError("empty trade calendar")

            today_text = now.strftime("%Y%m%d")
            if trade_dates[-1] == today_text and now.hour >= 15:
                return today_text

            if trade_dates[-1] == today_text and len(trade_dates) >= 2:
                return trade_dates[-2]

            return trade_dates[-1]
    except Exception:
        pass

    weekday = now.weekday()
    if weekday == 5:
        target = now - timedelta(days=1)
    elif weekday == 6:
        target = now - timedelta(days=2)
    elif weekday == 0:
        target = now - timedelta(days=3)
    else:
        target = now - timedelta(days=1)
    return target.strftime("%Y%m%d")


def fetch_stock_basic(limit: int = 20) -> pd.DataFrame:
    pro = get_tushare_client()
    df = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )
    return df.head(limit).copy()


def fetch_daily(trade_date: str, limit: int = 20) -> pd.DataFrame:
    pro = get_tushare_client()
    df = pro.daily(
        trade_date=trade_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    return df.head(limit).copy()


def fetch_daily_basic(trade_date: str, limit: int = 20) -> pd.DataFrame:
    pro = get_tushare_client()
    df = pro.daily_basic(
        trade_date=trade_date,
        fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,total_mv,circ_mv,pe,pb",
    )
    return df.head(limit).copy()


def fetch_probe_bundle(trade_date: str) -> dict[str, pd.DataFrame]:
    return {
        "stock_basic": fetch_stock_basic(),
        "daily": fetch_daily(trade_date=trade_date),
        "daily_basic": fetch_daily_basic(trade_date=trade_date),
    }


def fetch_stock_basic_full() -> pd.DataFrame:
    pro = get_tushare_client()
    return pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    ).copy()


def fetch_daily_for_trade_date(trade_date: str) -> pd.DataFrame:
    pro = get_tushare_client()
    return pro.daily(
        trade_date=trade_date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    ).copy()


def fetch_daily_basic_for_trade_date(trade_date: str) -> pd.DataFrame:
    pro = get_tushare_client()
    return pro.daily_basic(
        trade_date=trade_date,
        fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,total_mv,circ_mv,pe,pb",
    ).copy()


def fetch_cyq_perf_for_trade_date(trade_date: str) -> pd.DataFrame:
    pro = get_tushare_client()
    return pro.cyq_perf(trade_date=trade_date).copy()


def fetch_fund_basic_full() -> pd.DataFrame:
    pro = get_tushare_client()
    return pro.fund_basic(
        market="E",
        status="L",
    ).copy()


def fetch_fund_daily_for_trade_date(trade_date: str) -> pd.DataFrame:
    pro = get_tushare_client()
    return pro.fund_daily(
        trade_date=trade_date,
    ).copy()


def fetch_recent_trade_dates(limit: int = 70) -> list[str]:
    pro = get_tushare_client()
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
    calendar_df = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date, is_open="1")
    if calendar_df.empty:
        fallback = get_recent_trade_date_text()
        return [fallback]
    calendar_df = calendar_df.sort_values("cal_date", ascending=True).reset_index(drop=True)
    trade_dates = calendar_df["cal_date"].astype(str).tolist()
    return trade_dates[-limit:]


def fetch_trade_dates_between(start_date: str, end_date: str) -> list[str]:
    pro = get_tushare_client()
    calendar_df = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date, is_open="1")
    if calendar_df is None or calendar_df.empty:
        return []
    calendar_df = calendar_df.sort_values("cal_date", ascending=True).reset_index(drop=True)
    return calendar_df["cal_date"].astype(str).tolist()


def _chunk_trade_dates(trade_dates: list[str], chunk_size: int = 20) -> list[list[str]]:
    if chunk_size <= 0:
        return [trade_dates]
    return [trade_dates[index : index + chunk_size] for index in range(0, len(trade_dates), chunk_size)]


def _fetch_all_pages(fetch_page) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    offset = 0
    page_size = 6000
    while True:
        page_df = fetch_page(offset, page_size)
        if page_df is None or page_df.empty:
            break
        frames.append(page_df.copy())
        if len(page_df) < page_size:
            break
        offset += page_size
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_daily_history_by_ranges(trade_dates: list[str], chunk_size: int = 20) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for chunk in _chunk_trade_dates(trade_dates, chunk_size=chunk_size):
        if not chunk:
            continue
        daily_df = _fetch_all_pages(
            lambda offset, limit: pro.daily(
                start_date=chunk[0],
                end_date=chunk[-1],
                offset=offset,
                limit=limit,
                fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
            )
        )
        if daily_df is None or daily_df.empty:
            continue
        daily_df = daily_df.copy()
        daily_df.rename(
            columns={
                "pct_chg": "change_pct",
                "vol": "volume",
                "amount": "amount_thousand",
            },
            inplace=True,
        )
        for column in ("open", "high", "low", "close", "pre_close", "change", "change_pct", "volume", "amount_thousand"):
            if column in daily_df.columns:
                daily_df[column] = pd.to_numeric(daily_df[column], errors="coerce")
        daily_df["trade_date"] = pd.to_datetime(daily_df["trade_date"], format="%Y%m%d", errors="coerce")
        daily_df["amount"] = daily_df["amount_thousand"] * 1000
        frames.append(daily_df)

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_daily_basic_history_by_ranges(trade_dates: list[str], chunk_size: int = 20) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for chunk in _chunk_trade_dates(trade_dates, chunk_size=chunk_size):
        if not chunk:
            continue
        daily_basic_df = _fetch_all_pages(
            lambda offset, limit: pro.daily_basic(
                start_date=chunk[0],
                end_date=chunk[-1],
                offset=offset,
                limit=limit,
                fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,total_mv,circ_mv,pe,pb",
            )
        )
        if daily_basic_df is None or daily_basic_df.empty:
            continue
        daily_basic_df = daily_basic_df.copy()
        for column in ("turnover_rate", "turnover_rate_f", "volume_ratio", "total_mv", "circ_mv", "pe", "pb"):
            if column in daily_basic_df.columns:
                daily_basic_df[column] = pd.to_numeric(daily_basic_df[column], errors="coerce")
        daily_basic_df["trade_date"] = pd.to_datetime(daily_basic_df["trade_date"], format="%Y%m%d", errors="coerce")
        frames.append(daily_basic_df)

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_adj_factor_history_by_ranges(trade_dates: list[str], chunk_size: int = 20) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for chunk in _chunk_trade_dates(trade_dates, chunk_size=chunk_size):
        if not chunk:
            continue
        adj_df = _fetch_all_pages(
            lambda offset, limit: pro.adj_factor(
                start_date=chunk[0],
                end_date=chunk[-1],
                offset=offset,
                limit=limit,
            )
        )
        if adj_df is None or adj_df.empty:
            continue
        adj_df = adj_df.copy()
        adj_df["adj_factor"] = pd.to_numeric(adj_df["adj_factor"], errors="coerce")
        adj_df["trade_date"] = pd.to_datetime(adj_df["trade_date"], format="%Y%m%d", errors="coerce")
        frames.append(adj_df[["ts_code", "trade_date", "adj_factor"]])

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_daily_history_for_dates(trade_dates: list[str]) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for trade_date in trade_dates:
        daily_df = pro.daily(
            trade_date=trade_date,
            fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        )
        if daily_df is None or daily_df.empty:
            continue
        daily_df = daily_df.copy()
        daily_df.rename(
            columns={
                "pct_chg": "change_pct",
                "vol": "volume",
                "amount": "amount_thousand",
            },
            inplace=True,
        )
        for column in ("open", "high", "low", "close", "pre_close", "change", "change_pct", "volume", "amount_thousand"):
            if column in daily_df.columns:
                daily_df[column] = pd.to_numeric(daily_df[column], errors="coerce")
        daily_df["trade_date"] = pd.to_datetime(daily_df["trade_date"], format="%Y%m%d", errors="coerce")
        daily_df["amount"] = daily_df["amount_thousand"] * 1000
        frames.append(daily_df)

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_daily_basic_history_for_dates(trade_dates: list[str]) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for trade_date in trade_dates:
        daily_basic_df = pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,total_mv,circ_mv,pe,pb",
        )
        if daily_basic_df is None or daily_basic_df.empty:
            continue
        daily_basic_df = daily_basic_df.copy()
        for column in ("turnover_rate", "turnover_rate_f", "volume_ratio", "total_mv", "circ_mv", "pe", "pb"):
            if column in daily_basic_df.columns:
                daily_basic_df[column] = pd.to_numeric(daily_basic_df[column], errors="coerce")
        daily_basic_df["trade_date"] = pd.to_datetime(daily_basic_df["trade_date"], format="%Y%m%d", errors="coerce")
        frames.append(daily_basic_df)

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_adj_factor_history_for_dates(trade_dates: list[str]) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for trade_date in trade_dates:
        adj_df = pro.adj_factor(trade_date=trade_date)
        if adj_df is None or adj_df.empty:
            continue
        adj_df = adj_df.copy()
        adj_df["adj_factor"] = pd.to_numeric(adj_df["adj_factor"], errors="coerce")
        adj_df["trade_date"] = pd.to_datetime(adj_df["trade_date"], format="%Y%m%d", errors="coerce")
        frames.append(adj_df[["ts_code", "trade_date", "adj_factor"]])

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_cyq_perf_history_for_dates(trade_dates: list[str]) -> pd.DataFrame:
    pro = get_tushare_client()
    frames: list[pd.DataFrame] = []
    for trade_date in trade_dates:
        cyq_df = pro.cyq_perf(trade_date=trade_date)
        if cyq_df is None or cyq_df.empty:
            continue
        cyq_df = cyq_df.copy()
        for column in ("cost_15pct", "cost_50pct", "cost_85pct", "weight_avg", "winner_rate"):
            if column in cyq_df.columns:
                cyq_df[column] = pd.to_numeric(cyq_df[column], errors="coerce")
        cyq_df["trade_date"] = pd.to_datetime(cyq_df["trade_date"], format="%Y%m%d", errors="coerce")
        keep_columns = [
            column
            for column in ("ts_code", "trade_date", "cost_15pct", "cost_50pct", "cost_85pct", "weight_avg", "winner_rate")
            if column in cyq_df.columns
        ]
        frames.append(cyq_df[keep_columns])

    if not frames:
        return pd.DataFrame()
    history_df = pd.concat(frames, ignore_index=True)
    return history_df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def describe_probe_frame(dataset: str, df: pd.DataFrame) -> TushareProbeResult:
    return TushareProbeResult(
        dataset=dataset,
        ok=not df.empty,
        rows=int(len(df)),
        columns=[str(column) for column in df.columns.tolist()],
        detail="" if not df.empty else "Dataset returned 0 rows.",
    )


def run_probe(trade_date: str) -> list[TushareProbeResult]:
    frames = fetch_probe_bundle(trade_date=trade_date)
    return [describe_probe_frame(name, df) for name, df in frames.items()]
