from __future__ import annotations

import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

try:
    from .postclose_context_store import load_operations_review_context, save_operations_review_context
    from .postclose_holdings_service import HoldingsValidationError, load_saved_holdings_draft
    from .postclose_market_adapter import build_market_review_with_session
    from .postclose_operations_llm_service import generate_operations_review_with_llm
    from .postclose_session_service import normalize_review_session
    from .premarket_tushare_screen_service import fetch_tushare_snapshot
except ImportError:
    from postclose_context_store import load_operations_review_context, save_operations_review_context
    from postclose_holdings_service import HoldingsValidationError, load_saved_holdings_draft
    from postclose_market_adapter import build_market_review_with_session
    from postclose_operations_llm_service import generate_operations_review_with_llm
    from postclose_session_service import normalize_review_session
    from premarket_tushare_screen_service import fetch_tushare_snapshot


PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERDATA_DIR = PROJECT_ROOT / "result" / "userdata"
OPERATIONS_DRAFT_PATH = USERDATA_DIR / "postclose_operations_draft.json"
USERDATA_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return _sanitize_payload(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric_value = float(value)
        if math.isnan(numeric_value) or math.isinf(numeric_value):
            return None
        return value
    return value


def _normalize_symbol(raw_value: Any) -> str:
    text = str(raw_value or "").strip().upper()
    digits = "".join(char for char in text if char.isdigit())
    return digits if len(digits) == 6 else text


def _safe_float(raw_value: Any) -> float | None:
    text = str(raw_value or "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _save_operations_draft(items: list[dict[str, Any]]) -> None:
    payload = {
        "operations": items,
    }
    OPERATIONS_DRAFT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_saved_operations_draft() -> dict[str, Any]:
    if not OPERATIONS_DRAFT_PATH.exists():
        return {"status": "ok", "operations": []}
    try:
        payload = json.loads(OPERATIONS_DRAFT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "error", "operations": [], "message": "Failed to read saved operations draft."}
    return {"status": "ok", "operations": payload.get("operations") or []}


def _validate_operations_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise HoldingsValidationError("At least one operation record is required.")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(operations, start=1):
        if not isinstance(item, dict):
            raise HoldingsValidationError(f"Operation #{index} is not a valid object.")

        symbol = _normalize_symbol(item.get("symbol") or item.get("name"))
        side = str(item.get("side") or "").strip()
        price = _safe_float(item.get("price"))
        position_change = str(item.get("position_change") or "").strip()
        operate_time = str(item.get("operate_time") or "").strip()
        reason = str(item.get("reason") or "").strip()

        if not symbol:
            raise HoldingsValidationError(f"Operation #{index} is missing a symbol or name.")
        if not side:
            raise HoldingsValidationError(f"Operation #{index} is missing side.")
        if price is None:
            raise HoldingsValidationError(f"Operation #{index} is missing price.")
        if not position_change:
            raise HoldingsValidationError(f"Operation #{index} is missing position change.")
        if not operate_time:
            raise HoldingsValidationError(f"Operation #{index} is missing operate time.")
        if not reason:
            raise HoldingsValidationError(f"Operation #{index} is missing reason.")

        normalized.append(
            {
                "symbol": symbol,
                "side": side,
                "price": price,
                "position_change": position_change,
                "operate_time": operate_time,
                "reason": reason,
            }
        )

    return normalized


def _build_snapshot_lookup() -> dict[str, dict[str, Any]]:
    snapshot_df, _, _ = fetch_tushare_snapshot(force_refresh=False)
    lookup: dict[str, dict[str, Any]] = {}
    if snapshot_df.empty:
        return lookup
    for _, row in snapshot_df.iterrows():
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        lookup[symbol] = {
            "name": str(row.get("name") or symbol).strip(),
            "industry": str(row.get("industry") or "").strip(),
            "latest_price": row.get("latest_price"),
            "day_change_pct": row.get("change_pct"),
        }
    return lookup


def _build_fallback_operations_review(
    operations: list[dict[str, Any]],
    market_review: dict[str, Any],
    snapshot_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    market_detail = market_review.get("report_detail", {}) or {}
    market_fact_summary = market_review.get("fact_summary", {}) or {}
    market_focus = str(market_detail.get("focus") or "").strip()
    market_plan = str(market_detail.get("plan") or "").strip()
    mainlines = market_fact_summary.get("mainline_candidates", []) or []

    operation_reviews: list[dict[str, str]] = []
    risk_points: list[str] = []
    followups: list[str] = []
    aligned_count = 0

    for item in operations:
        fact = snapshot_lookup.get(item["symbol"], {})
        name = str(fact.get("name") or item["symbol"]).strip()
        day_change_pct = fact.get("day_change_pct")
        industry = str(fact.get("industry") or "").strip() or "Unknown"
        side = item["side"]
        reason = item["reason"]
        mainline_text = " / ".join([str(x).strip() for x in mainlines[:2] if str(x).strip()]) or "current market focus"

        if side == "买入":
            if day_change_pct is not None and float(day_change_pct) > 0:
                verdict = "Trend-following"
                aligned_count += 1
                review = (
                    f"{name} closed relatively strong on the day, so this buy is closer to trend-following. "
                    f"The key next step is verifying whether it is truly resonating with {mainline_text}."
                )
            else:
                verdict = "Counter-trend trial"
                review = (
                    f"{name} did not show strong same-day confirmation, so this buy looks more like an early setup "
                    "or a counter-trend trial and needs next-day validation."
                )
                risk_points.append(f"{name}: buy entry leaned counter-trend and should be rechecked if follow-through is weak.")
        else:
            if day_change_pct is not None and float(day_change_pct) < 0:
                verdict = "Risk control"
                aligned_count += 1
                review = (
                    f"{name} was relatively weak on the day, so the sell is easier to justify as risk control "
                    "rather than a rushed exit."
                )
            else:
                verdict = "Possible early exit"
                review = (
                    f"{name} did not clearly break down on the day, so this sell may be disciplined profit-taking, "
                    "but it may also carry early-exit risk."
                )
                risk_points.append(f"{name}: if it keeps strengthening next session, review whether the exit was premature.")

        operation_reviews.append(
            {
                "symbol": item["symbol"],
                "name": name,
                "verdict": verdict,
                "review": review,
                "reason_check": f"Original reason: {reason}",
                "next_step": "Next session, verify whether the trigger you wrote down is still valid before judging this trade.",
            }
        )
        followups.append(f"{name}: verify whether the logic behind this {side} action still holds next session.")

    summary = (
        f"Reviewed {len(operations)} operations today. {aligned_count} of them were closer to either trend-following "
        f"or disciplined risk control. {market_focus}".strip()
    )

    return {
        "summary": summary,
        "risk_flags": " ".join(risk_points[:3]) if risk_points else (market_focus or "Put each trade back into the market context before making a final judgment."),
        "plan": market_plan or "Tomorrow, first verify whether the trigger behind each trade is still valid.",
        "operations": operation_reviews,
        "next_watch": followups[:6],
    }


def _merge_operation_items(
    fallback_items: list[dict[str, Any]],
    llm_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for index, llm_item in enumerate(llm_items):
        fallback_item = fallback_items[index] if index < len(fallback_items) else {}
        merged.append(
            {
                **fallback_item,
                **llm_item,
                "industry": fallback_item.get("industry"),
            }
        )
    return merged


def build_postclose_operations_review(
    payload: dict[str, Any],
    force_refresh: bool = False,
    session: str | None = None,
) -> dict[str, Any]:
    review_session = normalize_review_session(session)
    operations = _validate_operations_payload(payload)
    if not force_refresh:
        cached = load_operations_review_context(review_session)
        cached_count = int((cached or {}).get("operations_input_count") or 0)
        if cached and cached_count == len(operations):
            return cached

    _save_operations_draft(operations)

    market_review = build_market_review_with_session(force_refresh=force_refresh, session=review_session)
    snapshot_lookup = _build_snapshot_lookup()
    holdings_draft = load_saved_holdings_draft()
    fallback_review = _build_fallback_operations_review(operations, market_review, snapshot_lookup)

    llm_status = {
        "enabled": False,
        "used": False,
        "provider": "deepseek",
        "model": None,
        "message": "LLM not configured. Using fallback operations review.",
    }
    review_payload = fallback_review
    errors: list[str] = []

    try:
        llm_review = generate_operations_review_with_llm(
            trade_date=str(market_review.get("trade_date") or ""),
            market_review=market_review,
            operations=operations,
            holdings_context={
                "draft_count": len(holdings_draft.get("holdings") or []),
                "holdings": holdings_draft.get("holdings") or [],
            },
            fallback_review=fallback_review,
        )
        review_payload = {
            **fallback_review,
            **llm_review,
            "operations": _merge_operation_items(
                fallback_review.get("operations", []),
                llm_review.get("operations", []),
            ),
            "next_watch": fallback_review.get("next_watch", []),
        }
        llm_meta = llm_review.get("llm_meta") or {}
        llm_status = {
            "enabled": True,
            "used": True,
            "provider": llm_meta.get("provider", "deepseek"),
            "model": llm_meta.get("model"),
            "message": "LLM operations review generated successfully.",
        }
    except Exception as exc:  # pragma: no cover
        errors.append(f"operations_review_llm: {exc}")

    response = {
        "status": "ok",
        "session": review_session,
        "trade_date": market_review.get("trade_date"),
        "operations_input_count": len(operations),
        "market_context": {
            "headline": market_review.get("report_detail", {}).get("close", ""),
            "focus": market_review.get("report_detail", {}).get("focus", ""),
            "plan": market_review.get("report_detail", {}).get("plan", ""),
        },
        "holdings_context": {
            "draft_count": len(holdings_draft.get("holdings") or []),
        },
        "review": review_payload,
        "llm_status": llm_status,
        "errors": errors,
    }
    save_operations_review_context(response, review_session)
    return _sanitize_payload(response)
