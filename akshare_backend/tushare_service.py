from __future__ import annotations

from typing import Any

try:
    from .tushare_provider import TushareConfigError, fetch_probe_bundle, get_recent_trade_date_text, run_probe
    from .premarket_tushare_screen_service import run_screen as run_tushare_screen
except ImportError:
    from tushare_provider import TushareConfigError, fetch_probe_bundle, get_recent_trade_date_text, run_probe
    from premarket_tushare_screen_service import run_screen as run_tushare_screen


def build_probe_response(trade_date: str | None = None) -> dict[str, Any]:
    resolved_trade_date = trade_date or get_recent_trade_date_text()
    try:
        items = [
            {
                "dataset": result.dataset,
                "ok": result.ok,
                "rows": result.rows,
                "columns": result.columns,
                "detail": result.detail,
            }
            for result in run_probe(trade_date=resolved_trade_date)
        ]
        return {
            "status": "ok",
            "provider": "tushare",
            "trade_date": resolved_trade_date,
            "items": items,
        }
    except TushareConfigError as exc:
        return {
            "status": "error",
            "provider": "tushare",
            "trade_date": resolved_trade_date,
            "message": "Tushare token is not configured.",
            "detail": str(exc),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "status": "error",
            "provider": "tushare",
            "trade_date": resolved_trade_date,
            "message": "Tushare probe failed.",
            "detail": str(exc),
        }


def build_sample_screen_response(trade_date: str | None = None) -> dict[str, Any]:
    resolved_trade_date = trade_date or get_recent_trade_date_text()
    try:
        response = run_tushare_screen(
            {
                "mode": "pre",
                "screen_depth": "fast",
                "market_scope": "沪深主板 + 创业板",
                "exclude_st": True,
                "exclude_paused": True,
                "exclude_bse": True,
                "exclude_new_listing_90d": False,
                "filters": {
                    "price_range": [8, 35],
                    "change_pct": [-2, 6],
                    "turnover_rate": [3, 18],
                    "volume_ratio": [1.2, 3.8],
                    "amount": [2e8, 8e9],
                    "total_market_cap": None,
                    "circulating_market_cap": None,
                    "amplitude": None,
                },
            }
        )
        return {
            "status": "ok",
            "provider": "tushare",
            "trade_date": response["stage_meta"].get("latest_trade_date", resolved_trade_date),
            "input_rows": response["first_round_count"],
            "matched_rows": response["final_result_count"],
            "items": response["results"],
            "note": "This is a minimal Tushare sample screening smoke test.",
        }
    except TushareConfigError as exc:
        return {
            "status": "error",
            "provider": "tushare",
            "trade_date": resolved_trade_date,
            "message": "Tushare token is not configured.",
            "detail": str(exc),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "status": "error",
            "provider": "tushare",
            "trade_date": resolved_trade_date,
            "message": "Tushare sample screening failed.",
            "detail": str(exc),
        }
