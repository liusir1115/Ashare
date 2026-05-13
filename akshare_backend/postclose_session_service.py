from __future__ import annotations

from datetime import datetime
from typing import Any


def normalize_review_session(session: str | None) -> str:
    return "midday" if str(session or "").strip().lower() == "midday" else "postclose"


def _safe_join(values: list[Any], fallback: str = "待补充") -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    return " / ".join(clean) if clean else fallback


def _normalize_trade_date_text(trade_date: Any) -> str:
    raw = str(trade_date or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw or "--"


def build_session_meta(session: str | None, trade_date: Any) -> dict[str, Any]:
    normalized = normalize_review_session(session)
    today_text = datetime.now().strftime("%Y%m%d")
    trade_date_raw = str(trade_date or "").strip()
    same_day = trade_date_raw == today_text

    if normalized == "midday":
        return {
            "requested_session": "midday",
            "served_session": "midday",
            "label": "午间快照",
            "summary_label": "午间观察",
            "action_label": "午后观察",
            "action_short_label": "午后重点",
            "trade_date_label": _normalize_trade_date_text(trade_date),
            "intraday_facts_ready": same_day,
            "note": (
                "当前模式用于午市休盘时快速整理观察框架；新闻层会尽量刷新到最新，"
                "但事实层仍受现有日线源限制，若当日盘中快照不可用，则会回退到最近可用交易日数据。"
            ),
        }

    return {
        "requested_session": "postclose",
        "served_session": "postclose",
        "label": "盘后复盘",
        "summary_label": "盘后复盘",
        "action_label": "次日预期",
        "action_short_label": "次日重点",
        "trade_date_label": _normalize_trade_date_text(trade_date),
        "intraday_facts_ready": True,
        "note": "当前模式默认基于收盘后事实层生成，适用于晚间复盘与次日计划准备。",
    }


def build_market_expectation(
    fact_summary: dict[str, Any],
    report_detail: dict[str, Any],
    session_meta: dict[str, Any],
    market_facts: dict[str, Any],
) -> dict[str, Any]:
    emotion = fact_summary.get("emotion_snapshot", {})
    mainlines = fact_summary.get("mainline_candidates", [])
    concepts = fact_summary.get("concept_candidates", [])
    hot_topics = fact_summary.get("hot_topics", [])
    limit_focus = emotion.get("limit_focus", [])
    action_label = session_meta.get("action_label", "次日预期")

    if session_meta.get("served_session") == "midday":
        headline = f"午后先盯 {_safe_join(limit_focus, '活口反馈')}，再确认 {_safe_join(mainlines, '主线承接')} 是否继续获得资金配合。"
    else:
        headline = f"次日先盯 {_safe_join(limit_focus, '活口反馈')}，再确认 {_safe_join(mainlines, '主线承接')} 是否继续获得资金配合。"

    return {
        "label": action_label,
        "headline": headline,
        "watchpoints": [
            f"主线承接：{_safe_join(mainlines, '待确认主线')}",
            f"扩散方向：{_safe_join(concepts, '待确认次主线')}",
            f"热门题材：{_safe_join(hot_topics, '待确认热点扩散')}",
        ],
        "risk_triggers": [
            f"高位情绪若明显转弱，最高板 {emotion.get('highest_board', 0)} 的承接会先出问题。",
            f"若跌停家数继续抬升到 {market_facts.get('limit_down_count', 0)} 以上同类水平，说明风险偏好仍未修复。",
        ],
        "execution_order": [
            f"先看 {_safe_join(limit_focus, '活口')} 是否继续获得承接。",
            f"再看 {_safe_join(mainlines, '主线')} 是否有资金回流与量能配合。",
            "最后处理偏离主线、没有新承接的持仓或观察标的。",
        ],
        "detail": str(report_detail.get("plan") or "").strip() or "待补充执行说明。",
    }


def build_holdings_next_actions(
    review_payload: dict[str, Any],
    holdings_facts: list[dict[str, Any]],
    session_meta: dict[str, Any],
) -> dict[str, Any]:
    next_watch = review_payload.get("next_watch") or []
    holdings = review_payload.get("holdings") or []
    prioritized = []
    for item in holdings[:5]:
        prioritized.append(
            {
                "symbol": str(item.get("symbol") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "verdict": str(item.get("verdict") or "").strip(),
                "next_step": str(item.get("next_step") or "").strip(),
            }
        )

    if not next_watch:
        next_watch = [str(item.get("next_step") or "").strip() for item in holdings[:4] if str(item.get("next_step") or "").strip()]

    hot_names = [str(item.get("name") or item.get("symbol") or "").strip() for item in holdings_facts[:3]]

    return {
        "label": session_meta.get("action_label", "次日预期"),
        "headline": str(review_payload.get("action_plan") or "").strip() or "待补充持仓处理顺序。",
        "watchpoints": next_watch[:4],
        "priority_holdings": prioritized,
        "note": f"当前优先处理 { _safe_join(hot_names, '核心持仓') } 等更接近主线或风险暴露更高的持仓。",
    }
