from __future__ import annotations

from typing import Any

try:
    from .postclose_market_service import build_postclose_market_review as build_base_postclose_market_review
    from .postclose_context_store import load_market_review_context, save_market_review_context
    from .postclose_session_service import build_market_expectation, build_session_meta, normalize_review_session
except ImportError:
    from postclose_market_service import build_postclose_market_review as build_base_postclose_market_review
    from postclose_context_store import load_market_review_context, save_market_review_context
    from postclose_session_service import build_market_expectation, build_session_meta, normalize_review_session


def build_market_review_with_session(force_refresh: bool = False, session: str | None = None) -> dict[str, Any]:
    review_session = normalize_review_session(session)
    if not force_refresh:
        cached = load_market_review_context(review_session)
        if cached:
            return cached

    payload = build_base_postclose_market_review(force_refresh=force_refresh)

    trade_date = payload.get("trade_date")
    session_meta = build_session_meta(review_session, trade_date)
    next_day_expectation = build_market_expectation(
        fact_summary=payload.get("fact_summary") or {},
        report_detail=payload.get("report_detail") or {},
        session_meta=session_meta,
        market_facts=payload.get("market", {}).get("facts") or {},
    )

    payload["session"] = review_session
    payload["session_meta"] = session_meta
    payload["next_day_expectation"] = next_day_expectation
    save_market_review_context(payload, review_session)
    return payload
