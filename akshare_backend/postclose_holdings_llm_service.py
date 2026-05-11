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
        "你是一个 A 股盘后持仓复盘助手。"
        "你只能基于提供给你的市场复盘和持仓事实做判断，不允许编造不存在的数据。"
        "如果行业属性和概念属性冲突，优先解释真正驱动近期涨跌的概念、主题和资金共振，而不是机械重复行业标签。"
        "输出必须是一个 JSON 对象，且只能包含这四个字段："
        "portfolio_summary, risk_flags, action_plan, holdings。"
        "其中 holdings 必须是数组，数组内每项都必须包含："
        "symbol, name, verdict, thesis, risk, next_step。"
        "语言要精简，结论优先，不要输出 Markdown，不要输出代码块。"
    )


def _build_user_prompt(
    *,
    trade_date: str,
    market_review: dict[str, Any],
    holdings_facts: list[dict[str, Any]],
    fallback_report: dict[str, Any],
) -> str:
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
        },
        "holdings_facts": holdings_facts,
        "fallback_report": fallback_report,
    }

    return (
        "请基于以上 A 股盘后市场上下文和用户持仓事实，输出正式的持仓复盘 JSON。\n"
        "要求：\n"
        "1. portfolio_summary 写组合总评，说明当前持仓与市场主线的关系。\n"
        "2. risk_flags 写当前最值得警惕的 2 到 3 个风险点，合并成一段字符串。\n"
        "3. action_plan 写次日持仓观察与处理建议，必须可执行。\n"
        "4. holdings 数组里每只股票都要逐条点评。\n"
        "5. verdict 要简短明确，例如“偏主线 / 中性观察 / 明显偏离”。\n"
        "6. thesis 的重点不是重复行业，而是解释这只股票近期真正的驱动更像什么：概念、主题、热点共振、资金承接还是独立波动。\n"
        "7. 如果 holdings_facts 里存在 concepts.driver_candidates、concepts.market_overlap、concepts.driver_evidence，请优先用它们判断真实驱动。\n"
        "8. 如事实不足，可以保守表达，但不能编造新的新闻、资金数据或板块地位。\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_llm_json(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("Holdings review output is not a JSON object.")

    portfolio_summary = str(parsed.get("portfolio_summary") or "").strip()
    risk_flags = str(parsed.get("risk_flags") or "").strip()
    action_plan = str(parsed.get("action_plan") or "").strip()
    holdings = parsed.get("holdings")

    if not portfolio_summary or not risk_flags or not action_plan:
        raise DeepSeekAPIError("Holdings review missing top-level fields.")
    if not isinstance(holdings, list) or not holdings:
        raise DeepSeekAPIError("Holdings review missing holdings array.")

    normalized_items: list[dict[str, str]] = []
    for item in holdings:
        if not isinstance(item, dict):
            raise DeepSeekAPIError("Holdings review item is not an object.")
        normalized = {
            "symbol": str(item.get("symbol") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "verdict": str(item.get("verdict") or "").strip(),
            "thesis": str(item.get("thesis") or "").strip(),
            "risk": str(item.get("risk") or "").strip(),
            "next_step": str(item.get("next_step") or "").strip(),
        }
        if not all(normalized.values()):
            raise DeepSeekAPIError("Holdings review item missing required fields.")
        normalized_items.append(normalized)

    return {
        "portfolio_summary": portfolio_summary,
        "risk_flags": risk_flags,
        "action_plan": action_plan,
        "holdings": normalized_items,
    }


def generate_holdings_review_with_llm(
    *,
    trade_date: str,
    market_review: dict[str, Any],
    holdings_facts: list[dict[str, Any]],
    fallback_report: dict[str, Any],
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
            holdings_facts=holdings_facts,
            fallback_report=fallback_report,
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
