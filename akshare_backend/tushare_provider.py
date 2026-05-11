from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

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
    return ts.pro_api(token)


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
