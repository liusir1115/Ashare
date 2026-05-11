from __future__ import annotations

import json
from typing import Any

try:
    from .deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from .llm_config import load_llm_settings
except ImportError:
    from deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from llm_config import load_llm_settings


SECTION_KEYS = [
    "close",
    "environment",
    "funds",
    "focus",
    "rotation",
    "emotion",
    "reason",
    "plan",
]


def _build_system_prompt() -> str:
    return (
        "你是一个A股盘后复盘助手。"
        "你只能基于用户提供的结构化事实写复盘，不允许编造不存在的数据。"
        "你必须严格区分事实与解释，语言精简，结论优先。"
        "你需要输出一个JSON对象，只能包含以下8个字段："
        "close, environment, funds, focus, rotation, emotion, reason, plan。"
        "每个字段都必须是中文字符串。"
        "不要输出Markdown，不要输出代码块，不要补充额外字段。"
    )


def _build_user_prompt(
    *,
    trade_date: str,
    market: dict[str, Any],
    postclose_facts: dict[str, Any],
    fact_summary: dict[str, Any],
    news: dict[str, Any],
    fallback_report_detail: dict[str, Any],
) -> str:
    payload = {
        "trade_date": trade_date,
        "market": market,
        "postclose_facts": postclose_facts,
        "fact_summary": fact_summary,
        "news": news,
        "fallback_report_detail": fallback_report_detail,
    }

    return (
        "请基于以下A股盘后事实层数据，生成正式复盘解释层JSON。\n"
        "要求：\n"
        "1. 不能编造事实层没有给出的结论。\n"
        "2. 可以归纳，但不能伪造具体股票、数字和原因链。\n"
        "3. close 要像真正的总收口。\n"
        "4. reason 要重点解释为什么今天市场会走成这样，以及哪些新闻或驱动更值得保留。\n"
        "5. plan 要写成次日可执行观察清单，而不是空泛鼓励。\n"
        "6. 如果某项事实不足，可以保守表达，但不要说“无法判断”。\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_llm_json(text: str) -> dict[str, str]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("LLM output is not a JSON object.")

    result: dict[str, str] = {}
    for key in SECTION_KEYS:
        value = str(parsed.get(key) or "").strip()
        if not value:
            raise DeepSeekAPIError(f"LLM output missing required section: {key}")
        result[key] = value
    return result


def generate_postclose_report_detail_with_llm(
    *,
    trade_date: str,
    market: dict[str, Any],
    postclose_facts: dict[str, Any],
    fact_summary: dict[str, Any],
    news: dict[str, Any],
    fallback_report_detail: dict[str, Any],
) -> dict[str, Any]:
    settings = load_llm_settings()
    if not settings.enabled:
        raise DeepSeekAPIError("DeepSeek API key is not configured.")

    result = chat_completion_with_timeout(
        settings,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_user_prompt(
            trade_date=trade_date,
            market=market,
            postclose_facts=postclose_facts,
            fact_summary=fact_summary,
            news=news,
            fallback_report_detail=fallback_report_detail,
        ),
        response_format={"type": "json_object"},
        timeout_seconds=min(settings.timeout_seconds, 35.0),
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
