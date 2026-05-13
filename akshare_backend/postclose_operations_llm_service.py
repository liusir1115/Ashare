from __future__ import annotations

import json
from typing import Any

try:
    from .deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from .llm_config import load_llm_settings
except ImportError:
    from deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from llm_config import load_llm_settings


def _build_system_prompt() -> str:
    return (
        "You are an A-share post-close trade review assistant. "
        "You may only judge based on the provided market review, operation records, holdings context, and fallback facts. "
        "Do not invent any news, flows, board status, or stock facts that are not present in the input. "
        "Your main task is to judge whether each operation matched trend, market focus, and risk control. "
        "Each operation includes a side_label field with BUY or SELL. You must follow side_label literally. "
        "You must preserve trade direction exactly: a buy must be reviewed as a buy, and a sell must be reviewed as a sell. "
        "Output must be a single JSON object with exactly these top-level fields: summary, risk_flags, plan, operations. "
        "operations must be an array, and each item must include: symbol, name, verdict, review, reason_check, next_step. "
        "Do not output markdown or code fences."
    )


def _build_user_prompt(
    *,
    trade_date: str,
    market_review: dict[str, Any],
    operations: list[dict[str, Any]],
    holdings_context: dict[str, Any],
    fallback_review: dict[str, Any],
) -> str:
    normalized_operations = []
    for item in operations:
        side = str(item.get("side") or "").strip()
        normalized_operations.append(
            {
                **item,
                "side_label": "BUY" if side == "买入" else "SELL" if side == "卖出" else side.upper(),
            }
        )

    payload = {
        "trade_date": trade_date,
        "market_review": {
            "headline": market_review.get("report_detail", {}).get("close", ""),
            "focus": market_review.get("report_detail", {}).get("focus", ""),
            "rotation": market_review.get("report_detail", {}).get("rotation", ""),
            "emotion": market_review.get("report_detail", {}).get("emotion", ""),
            "plan": market_review.get("report_detail", {}).get("plan", ""),
            "fact_summary": market_review.get("fact_summary", {}),
            "market_facts": market_review.get("market", {}).get("facts", {}),
            "next_day_expectation": market_review.get("next_day_expectation", {}),
        },
        "operations": normalized_operations,
        "holdings_context": holdings_context,
        "fallback_review": fallback_review,
    }
    return (
        "Generate a formal post-close operations review as JSON.\n"
        "Requirements:\n"
        "1. summary: overall evaluation of whether today's operations matched the market environment.\n"
        "2. risk_flags: 2 to 3 concise issues worth reviewing, such as mistakes, hesitation, impulse, or plan drift.\n"
        "3. plan: what to verify next session to confirm whether today's operations were valid.\n"
        "4. operations: review each operation one by one.\n"
        "5. Each operation review must stay consistent with the original side_label field. Do not reverse buy and sell.\n"
        "6. review should explain why the action was trend-following, counter-trend, disciplined, or premature.\n"
        "7. reason_check should judge whether the user's original reason matched the market context and plan.\n"
        "8. If facts are limited, stay conservative instead of inventing details.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_llm_json(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("Operations review output is not a JSON object.")

    summary = str(parsed.get("summary") or "").strip()
    risk_flags = str(parsed.get("risk_flags") or "").strip()
    plan = str(parsed.get("plan") or "").strip()
    operations = parsed.get("operations")

    if not summary or not risk_flags or not plan:
        raise DeepSeekAPIError("Operations review missing top-level fields.")
    if not isinstance(operations, list) or not operations:
        raise DeepSeekAPIError("Operations review missing operations array.")

    normalized_items: list[dict[str, str]] = []
    for item in operations:
        if not isinstance(item, dict):
            raise DeepSeekAPIError("Operations review item is not an object.")
        normalized = {
            "symbol": str(item.get("symbol") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "verdict": str(item.get("verdict") or "").strip(),
            "review": str(item.get("review") or "").strip(),
            "reason_check": str(item.get("reason_check") or "").strip(),
            "next_step": str(item.get("next_step") or "").strip(),
        }
        if not all(normalized.values()):
            raise DeepSeekAPIError("Operations review item missing required fields.")
        normalized_items.append(normalized)

    return {
        "summary": summary,
        "risk_flags": risk_flags,
        "plan": plan,
        "operations": normalized_items,
    }


def generate_operations_review_with_llm(
    *,
    trade_date: str,
    market_review: dict[str, Any],
    operations: list[dict[str, Any]],
    holdings_context: dict[str, Any],
    fallback_review: dict[str, Any],
) -> dict[str, Any]:
    settings = load_llm_settings()
    if not settings.enabled:
        raise DeepSeekAPIError("DeepSeek API key is not configured.")

    result = chat_completion_with_timeout(
        settings,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_user_prompt(
            trade_date=trade_date,
            market_review=market_review,
            operations=operations,
            holdings_context=holdings_context,
            fallback_review=fallback_review,
        ),
        response_format={"type": "json_object"},
        timeout_seconds=min(settings.timeout_seconds, 28.0),
    )

    parsed = _parse_llm_json(result["content"])
    return {
        **parsed,
        "llm_meta": {
            "provider": settings.provider,
            "model": settings.model,
            "enabled": True,
        },
    }
