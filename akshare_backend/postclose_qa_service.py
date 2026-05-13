from __future__ import annotations

import json
from typing import Any

try:
    from .postclose_context_store import load_holdings_review_context, load_market_review_context
    from .deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from .llm_config import load_llm_settings
    from .postclose_holdings_service import build_postclose_holdings_review, load_saved_holdings_draft
    from .postclose_market_adapter import build_market_review_with_session
    from .postclose_session_service import normalize_review_session
except ImportError:
    from postclose_context_store import load_holdings_review_context, load_market_review_context
    from deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from llm_config import load_llm_settings
    from postclose_holdings_service import build_postclose_holdings_review, load_saved_holdings_draft
    from postclose_market_adapter import build_market_review_with_session
    from postclose_session_service import normalize_review_session


def _build_system_prompt() -> str:
    return (
        "你是A股盘后复盘问答助手。"
        "你只能基于提供给你的市场复盘、持仓复盘和结构化事实回答，不能编造不存在的数据。"
        "回答要精简、结论优先、证据可追溯。"
        "输出必须是一个JSON对象，且只包含 answer, evidence, followups 三个字段。"
        "answer 是中文字符串；evidence 和 followups 都是字符串数组。"
        "不要输出Markdown，不要输出代码块，不要补充额外字段。"
    )


def _build_user_prompt(
    *,
    question: str,
    session: str,
    market_review: dict[str, Any],
    holdings_review: dict[str, Any] | None,
    holdings_draft: dict[str, Any],
) -> str:
    payload = {
        "session": session,
        "question": question,
        "market_review": {
            "trade_date": market_review.get("trade_date"),
            "session_meta": market_review.get("session_meta"),
            "fact_summary": market_review.get("fact_summary"),
            "next_day_expectation": market_review.get("next_day_expectation"),
            "report_detail": market_review.get("report_detail"),
            "market_facts": market_review.get("market", {}).get("facts", {}),
        },
        "holdings_review": holdings_review,
        "holdings_draft": holdings_draft,
    }
    return (
        "请基于以下盘后上下文回答用户问题。\n"
        "要求：\n"
        "1. answer 先给结论，再补一句执行建议。\n"
        "2. evidence 提供 2 到 4 条证据，尽量引用主线、情绪、资金、持仓驱动等现有字段。\n"
        "3. followups 提供 1 到 3 个下一步值得继续问的问题。\n"
        "4. 如果用户问到持仓，而当前没有持仓复盘结果，可以基于 holdings_draft 保守回答，但必须说明依据更弱。\n"
        "5. 不要编造新的新闻、资金数字或个股事实。\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_response(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("Postclose QA output is not a JSON object.")

    answer = str(parsed.get("answer") or "").strip()
    evidence = parsed.get("evidence") or []
    followups = parsed.get("followups") or []
    if not answer:
        raise DeepSeekAPIError("Postclose QA output missing answer.")
    if not isinstance(evidence, list):
        raise DeepSeekAPIError("Postclose QA evidence must be a list.")
    if not isinstance(followups, list):
        raise DeepSeekAPIError("Postclose QA followups must be a list.")

    return {
        "answer": answer,
        "evidence": [str(item).strip() for item in evidence if str(item).strip()][:4],
        "followups": [str(item).strip() for item in followups if str(item).strip()][:3],
    }


def _build_fallback_answer(
    question: str,
    market_review: dict[str, Any],
    holdings_review: dict[str, Any] | None,
    holdings_draft: dict[str, Any],
) -> dict[str, Any]:
    report_detail = market_review.get("report_detail", {})
    next_expectation = market_review.get("next_day_expectation", {})
    holdings_block = holdings_review.get("review", {}) if holdings_review else {}
    draft_items = holdings_draft.get("holdings") or []

    answer = str(report_detail.get("focus") or "").strip() or str(report_detail.get("close") or "").strip()
    if not answer:
        answer = "当前先以市场主线承接和高位情绪反馈为主，优先确认最强方向是否继续获得资金配合。"

    evidence = [
        str(next_expectation.get("headline") or "").strip(),
        str(report_detail.get("plan") or "").strip(),
        str(holdings_block.get("action_plan") or "").strip(),
    ]
    if draft_items and not holdings_review:
        first_symbol = str(draft_items[0].get("symbol") or draft_items[0].get("name") or "").strip()
        if first_symbol:
            evidence.append(f"当前仅检测到持仓草稿 {first_symbol}，尚未正式生成持仓复盘，所以个股判断依据较弱。")

    followups = [
        "明天先看哪些承接验证条件？",
        "我的持仓里谁更偏离主线？",
        "如果高位情绪转弱，先处理哪一类标的？",
    ]

    question_text = question.strip()
    if question_text:
        answer = f"{answer} 当前这条回答是围绕“{question_text}”做的保守收敛。"

    return {
        "answer": answer,
        "evidence": [item for item in evidence if item][:4],
        "followups": followups,
    }


def build_postclose_qa(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("Question is required.")

    session = normalize_review_session(payload.get("session"))
    include_holdings = bool(payload.get("include_holdings", True))

    market_review = load_market_review_context(session) or build_market_review_with_session(force_refresh=False, session=session)
    holdings_draft = load_saved_holdings_draft()
    holdings_review = load_holdings_review_context(session) if include_holdings else None
    errors: list[str] = []

    if include_holdings and holdings_review is None and (holdings_draft.get("holdings") or []):
        try:
            holdings_review = build_postclose_holdings_review(
                {"holdings": holdings_draft.get("holdings") or []},
                force_refresh=False,
                session=session,
            )
        except Exception as exc:  # pragma: no cover
            errors.append(f"holdings_context: {exc}")

    llm_status = {
        "enabled": False,
        "used": False,
        "provider": "deepseek",
        "model": None,
        "message": "LLM not configured. Using fallback QA answer.",
    }
    result = _build_fallback_answer(question, market_review, holdings_review, holdings_draft)

    try:
        settings = load_llm_settings()
        if not settings.enabled:
            raise DeepSeekAPIError("DeepSeek API key is not configured.")
        llm_result = chat_completion_with_timeout(
            settings,
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(
                question=question,
                session=session,
                market_review=market_review,
                holdings_review=holdings_review,
                holdings_draft=holdings_draft,
            ),
            response_format={"type": "json_object"},
            timeout_seconds=min(settings.timeout_seconds, 24.0),
        )
        result = _parse_response(llm_result["content"])
        llm_status = {
            "enabled": True,
            "used": True,
            "provider": settings.provider,
            "model": settings.model,
            "message": "LLM postclose QA generated successfully.",
        }
    except Exception as exc:  # pragma: no cover
        errors.append(f"postclose_qa_llm: {exc}")

    return {
        "status": "ok",
        "session": session,
        "question": question,
        "answer": result["answer"],
        "evidence": result["evidence"],
        "followups": result["followups"],
        "market_context": {
            "trade_date": market_review.get("trade_date"),
            "headline": market_review.get("report_detail", {}).get("close", ""),
            "next_day_expectation": market_review.get("next_day_expectation"),
        },
        "holdings_context": {
            "draft_count": len(holdings_draft.get("holdings") or []),
            "review_loaded": holdings_review is not None,
        },
        "llm_status": llm_status,
        "errors": errors,
    }
