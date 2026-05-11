from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import akshare as ak
import pandas as pd

try:
    from .premarket_shared import infer_market
except ImportError:
    from premarket_shared import infer_market


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

SPOT_CACHE_TTL_SECONDS = 180
SPOT_CACHE: dict[str, Any] = {"expires_at": 0.0, "data": None}


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


def probe_snapshot() -> dict[str, Any]:
    df = fetch_spot_snapshot()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": int(len(df)),
        "columns": list(df.columns),
        "sample": df.head(1).to_dict(orient="records"),
    }
