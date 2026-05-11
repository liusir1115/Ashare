from __future__ import annotations

from typing import Any

try:
    from .premarket_news_service import get_market_news_brief
except ImportError:
    from premarket_news_service import get_market_news_brief


def fetch_news_snapshot(force_refresh: bool = False) -> dict[str, Any]:
    payload = get_market_news_brief(force_refresh=force_refresh)
    items = payload.get("items", [])

    return {
        "status": payload.get("status", "degraded"),
        "message": payload.get("message", ""),
        "brief_date": payload.get("brief_date"),
        "source": payload.get("source"),
        "source_label": payload.get("source_label"),
        "updated_at": payload.get("updated_at"),
        "items": items[:6],
    }
