from __future__ import annotations

import math
from datetime import datetime
from numbers import Real
from typing import Any

try:
    from .market_data_provider import fetch_market_snapshot
    from .news_provider import fetch_news_snapshot
    from .postclose_fact_builder import build_postclose_fact_summary
    from .postclose_llm_service import generate_postclose_report_detail_with_llm
    from .postclose_session_service import build_market_expectation, build_session_meta, normalize_review_session
    from .postclose_tushare_provider import fetch_postclose_facts
except ImportError:
    from market_data_provider import fetch_market_snapshot
    from news_provider import fetch_news_snapshot
    from postclose_fact_builder import build_postclose_fact_summary
    from postclose_llm_service import generate_postclose_report_detail_with_llm
    from postclose_session_service import build_market_expectation, build_session_meta, normalize_review_session
    from postclose_tushare_provider import fetch_postclose_facts


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if value is None:
        return None
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except TypeError:
            pass
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


def _safe_join(values: list[str], fallback: str = "待补充") -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    return " / ".join(clean) if clean else fallback


def _format_pct(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "--"


def _format_yi(value: Any) -> str:
    try:
        return f"{float(value) / 1e8:.2f} 亿元"
    except (TypeError, ValueError):
        return "--"


def _format_net_amount(value: Any) -> str:
    try:
        numeric = float(value)
        return f"{numeric:.2f} 亿"
    except (TypeError, ValueError):
        return "--"


def _format_top_lines(
    items: list[dict[str, Any]],
    *,
    name_key: str,
    metric_key: str | None = None,
    limit: int = 5,
) -> list[str]:
    lines: list[str] = []
    for item in items[:limit]:
        name = str(item.get(name_key) or item.get("name") or item.get("industry") or "--").strip()
        if metric_key is None:
          lines.append(name)
          continue
        metric = item.get(metric_key)
        metric_text = _format_net_amount(metric)
        lines.append(f"{name}（净额 {metric_text}）")
    return lines


def _format_limit_focus_lines(items: list[dict[str, Any]], limit: int = 6) -> list[str]:
    lines: list[str] = []
    for item in items[:limit]:
        name = str(item.get("name") or "--").strip()
        days = item.get("days", "--")
        up_nums = item.get("up_nums", "--")
        up_stat = item.get("up_stat", "--")
        lines.append(f"{name}（连板天数 {days}，涨停家数 {up_nums}，结构 {up_stat}）")
    return lines


def _format_limit_up_lines(items: list[dict[str, Any]], limit: int = 6) -> list[str]:
    lines: list[str] = []
    for item in items[:limit]:
        name = str(item.get("name") or "--").strip()
        industry = str(item.get("industry") or "--").strip()
        limit_times = item.get("limit_times", "--")
        amount_text = _format_yi(item.get("amount"))
        lines.append(f"{name}（{industry}，封板次数 {limit_times}，成交额 {amount_text}）")
    return lines


def _format_hot_stock_lines(items: list[dict[str, Any]], limit: int = 8) -> list[str]:
    lines: list[str] = []
    for item in items[:limit]:
        name = str(item.get("ts_name") or item.get("name") or "--").strip()
        concept = str(item.get("concept") or "待补充").strip()
        pct_change = item.get("pct_change")
        pct_text = _format_pct(pct_change)
        lines.append(f"{name}（题材 {concept[:40]}，涨跌幅 {pct_text}）")
    return lines


def _build_bullet_lines(lines: list[str], fallback: str = "暂无补充。") -> str:
    clean = [str(line).strip() for line in lines if str(line).strip()]
    if not clean:
        return fallback
    return "\n".join([f"• {line}" for line in clean])


def _build_summary_cards(facts: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "title": "市场宽度",
            "value": f"上涨 {facts.get('up_count', 0)} / 下跌 {facts.get('down_count', 0)}",
            "detail": f"平盘 {facts.get('flat_count', 0)} / 样本 {facts.get('universe_count', 0)}",
        },
        {
            "title": "量能概览",
            "value": facts.get("turnover_total_text", "--"),
            "detail": f"全市场平均涨跌幅 {facts.get('avg_change_pct', 0)}%",
        },
        {
            "title": "涨停结构",
            "value": f"涨停 {facts.get('limit_up_count', 0)}",
            "detail": f"跌停 {facts.get('limit_down_count', 0)}",
        },
        {
            "title": "解释层",
            "value": "已生成",
            "detail": "市场总复盘会同时输出事实层和解释层，供后续持仓复盘继续引用。",
        },
    ]


def _build_report_detail(
    market_payload: dict[str, Any],
    postclose_facts_payload: dict[str, Any],
    fact_summary: dict[str, Any],
    news_payload: dict[str, Any],
) -> dict[str, Any]:
    market_facts = market_payload.get("facts", {})
    emotion = fact_summary.get("emotion_snapshot", {})

    industry_inflow = postclose_facts_payload.get("moneyflow_ind", {}).get("top_inflow", [])
    industry_outflow = postclose_facts_payload.get("moneyflow_ind", {}).get("top_outflow", [])
    concept_inflow = postclose_facts_payload.get("moneyflow_concept", {}).get("top_inflow", [])
    concept_outflow = postclose_facts_payload.get("moneyflow_concept", {}).get("top_outflow", [])
    limit_focus_items = postclose_facts_payload.get("limit_concepts", {}).get("items", [])
    limit_up_items = postclose_facts_payload.get("limit_structure", {}).get("top_limit_up", [])
    hotspot_items = postclose_facts_payload.get("hotspots", {}).get("top_ranked", [])
    news_items = news_payload.get("items", [])

    mainline_text = _safe_join(fact_summary.get("mainline_candidates", []))
    concept_text = _safe_join(fact_summary.get("concept_candidates", []))
    hot_topic_text = _safe_join(fact_summary.get("hot_topics", []))
    limit_focus_text = _safe_join(emotion.get("limit_focus", []))

    strongest_names = _safe_join([item.get("name", "") for item in market_facts.get("strongest", [])], "待补充")
    weakest_names = _safe_join([item.get("name", "") for item in market_facts.get("weakest", [])], "待补充")
    leader_names = _safe_join([item.get("name", "") for item in market_facts.get("leaders", [])], "待补充")

    industry_inflow_lines = _format_top_lines(industry_inflow, name_key="industry", metric_key="net_amount", limit=6)
    industry_outflow_lines = _format_top_lines(industry_outflow, name_key="industry", metric_key="net_amount", limit=6)
    concept_inflow_lines = _format_top_lines(concept_inflow, name_key="concept_name", metric_key="net_amount", limit=6)
    concept_outflow_lines = _format_top_lines(concept_outflow, name_key="concept_name", metric_key="net_amount", limit=6)
    limit_focus_lines = _format_limit_focus_lines(limit_focus_items)
    limit_up_lines = _format_limit_up_lines(limit_up_items)
    hot_stock_lines = _format_hot_stock_lines(hotspot_items)
    news_lines = [
        f"{item.get('title', '--')}：{str(item.get('summary') or '').strip()}"
        for item in news_items[:5]
    ]

    close = (
        f"今天的市场总收口可以概括为：资金仍然围绕 {mainline_text} 做主攻，"
        f"次级承接主要围绕 {concept_text} 展开，热点扩散集中在 {hot_topic_text}。"
        f" 从市场宽度和量能看，上涨 {market_facts.get('up_count', 0)} 家，下跌 {market_facts.get('down_count', 0)} 家，"
        f"成交额 {market_facts.get('turnover_total_text', '--')}，更像结构性抱团而不是全面普涨。"
    )

    environment = (
        f"交易日 {postclose_facts_payload.get('trade_date', '--')} 的市场环境可以拆成四层去看。"
        f"\n• 宽度：上涨 {market_facts.get('up_count', 0)} 家，下跌 {market_facts.get('down_count', 0)} 家，平盘 {market_facts.get('flat_count', 0)} 家。"
        f"\n• 量能：全市场成交额 {market_facts.get('turnover_total_text', '--')}，平均涨跌幅 {_format_pct(market_facts.get('avg_change_pct', 0))}。"
        f"\n• 强弱样本：强势代表包括 {strongest_names}，弱势代表包括 {weakest_names}。"
        f"\n• 成交核心：高成交样本主要集中在 {leader_names}。"
        "\n这说明今天不是普遍性赚钱环境，而是更偏向少数方向吸走注意力和成交。"
    )

    funds = (
        "资金层要分成净流入、净流出、主攻方向和防守方向四部分去看。"
        f"\n• 行业净流入前排：\n{_build_bullet_lines(industry_inflow_lines)}"
        f"\n• 行业净流出前排：\n{_build_bullet_lines(industry_outflow_lines)}"
        f"\n• 概念净流入前排：\n{_build_bullet_lines(concept_inflow_lines)}"
        f"\n• 概念净流出前排：\n{_build_bullet_lines(concept_outflow_lines)}"
        f"\n综合来看，今天最值得保留的资金主攻方向仍然是 {mainline_text}，而 {concept_text} 更像边缘承接或补位。"
    )

    focus = (
        f"盘后最值得保留的四个判断是：主线先看 {mainline_text}；"
        f"次主线先看 {concept_text}；风险边界先看最高板 {emotion.get('highest_board', 0)} 和跌停 {market_facts.get('limit_down_count', 0)}；"
        f"次日重点先看 {limit_focus_text} 是否继续获得承接。"
    )

    rotation = (
        "主线与轮动必须拆开看，不能把一切上涨都当成同一条线。"
        f"\n\n• 主线：{mainline_text}"
        f"\n\n• 次主线：{concept_text}"
        f"\n\n• 热点题材：{hot_topic_text}"
        f"\n\n• 热门样本：\n{_build_bullet_lines(hot_stock_lines)}"
        "\n\n• 结构结论：从结构上看，更像少数方向吸走资金，其他方向更多是陪跑式轮动。次日需要确认主线是否继续强化，还是开始走向高低切。"
    )

    emotion_text = (
        "情绪层不能只看涨停家数，必须和最高板、活口、连板结构一起看。"
        f"\n• 涨停家数：{emotion.get('limit_up_count', 0)}"
        f"\n• 最高板：{emotion.get('highest_board', 0)}"
        f"\n• 跌停家数：{market_facts.get('limit_down_count', 0)}"
        f"\n• 活口焦点：{limit_focus_text}"
        f"\n• 连板结构明细：\n{_build_bullet_lines(limit_focus_lines)}"
        f"\n• 高辨识度涨停样本：\n{_build_bullet_lines(limit_up_lines)}"
        "\n如果活口继续集中，说明短线仍有聚焦；如果高位迅速掉队，就要警惕情绪退潮。"
    )

    reason = (
        f"驱动层当前可引用的新闻来源主要来自 {news_payload.get('source_label', '新闻接口')}。"
        f"\n• 今日重点快讯：\n{_build_bullet_lines(news_lines)}"
        f"\n• 市场之所以走成这样，本质上是资金把注意力集中到了 {mainline_text}，"
        f"而 {hot_topic_text} 提供了题材层面的扩散载体。"
        "\n新闻在这里的作用不是替代市场，而是补充解释资金为什么会在这些方向形成共识。"
    )

    plan = (
        "次日执行先做三件事。"
        f"\n• 第一，先看 {limit_focus_text} 是否继续获得承接，确认短线情绪没有快速熄火。"
        f"\n• 第二，再看 {mainline_text} 是否继续获得资金回流和成交配合。"
        "\n• 第三，确认失败轮动方向是否继续回落，避免把回流错判成新主线。"
        "\n如果前两项成立，可以继续围绕强势主线跟踪；如果任一项明显失效，就要主动降低预期。"
    )

    return {
        "close": close,
        "environment": environment,
        "funds": funds,
        "focus": focus,
        "rotation": rotation,
        "emotion": emotion_text,
        "reason": reason,
        "plan": plan,
        "source_notes": {
            "trade_date": postclose_facts_payload.get("trade_date", "--"),
            "market": "Tushare 日线行情快照（daily + daily_basic 聚合）",
            "postclose_facts": "Tushare 同花顺行业资金、概念资金、涨停结构、连板题材、热股榜",
            "news": news_payload.get("source_label") or "新闻接口",
            "news_updated_at": news_payload.get("updated_at"),
        },
    }


def build_postclose_market_review(force_refresh: bool = False) -> dict[str, Any]:
    fallback_trade_date = datetime.now().strftime("%Y-%m-%d")
    errors: list[str] = []

    try:
        market_payload = fetch_market_snapshot(force_refresh=force_refresh)
    except Exception as exc:  # pragma: no cover
        market_payload = {
            "status": "fail",
            "message": "Tushare 市场快照获取失败。",
            "facts": {},
        }
        errors.append(f"market_snapshot: {exc}")

    try:
        postclose_facts_payload = fetch_postclose_facts()
    except Exception as exc:  # pragma: no cover
        postclose_facts_payload = {
            "trade_date": fallback_trade_date,
            "moneyflow_ind": {"rows": 0, "top_inflow": [], "top_outflow": []},
            "moneyflow_concept": {"rows": 0, "top_inflow": [], "top_outflow": []},
            "limit_structure": {"rows": 0, "top_limit_up": [], "summary": {"limit_up_count": 0, "highest_board": 0}},
            "limit_concepts": {"rows": 0, "items": []},
            "hotspots": {"rows": 0, "top_ranked": []},
        }
        errors.append(f"postclose_facts: {exc}")

    try:
        news_payload = fetch_news_snapshot(force_refresh=force_refresh)
    except Exception as exc:  # pragma: no cover
        news_payload = {
            "status": "fail",
            "message": "新闻摘要获取失败。",
            "items": [],
        }
        errors.append(f"news_snapshot: {exc}")

    market_status = market_payload.get("status", "fail")
    news_status = news_payload.get("status", "fail")

    overall_status = "ok"
    if "fail" in {market_status, news_status}:
        overall_status = "degraded"
    if market_status == "fail" and news_status == "fail":
        overall_status = "fail"

    facts = market_payload.get("facts", {})
    fact_summary = build_postclose_fact_summary(postclose_facts_payload)

    snapshot_limit_up_count = int(facts.get("limit_up_count") or 0)
    emotion_snapshot = fact_summary.get("emotion_snapshot", {})
    if int(emotion_snapshot.get("limit_up_count") or 0) == 0 and snapshot_limit_up_count > 0:
        emotion_snapshot["limit_up_count"] = snapshot_limit_up_count
        fact_summary["emotion_snapshot"] = emotion_snapshot
        postclose_facts_payload.setdefault("limit_structure", {}).setdefault("summary", {})["limit_up_count"] = snapshot_limit_up_count

    fallback_report_detail = _build_report_detail(
        market_payload=market_payload,
        postclose_facts_payload=postclose_facts_payload,
        fact_summary=fact_summary,
        news_payload=news_payload,
    )
    resolved_trade_date = postclose_facts_payload.get("trade_date") or facts.get("trade_date") or fallback_trade_date
    report_detail = fallback_report_detail
    llm_status = {
        "enabled": False,
        "used": False,
        "provider": "deepseek",
        "model": None,
        "message": "LLM not configured. Using fallback report detail.",
    }

    try:
        llm_report_detail = generate_postclose_report_detail_with_llm(
            trade_date=resolved_trade_date,
            market=market_payload,
            postclose_facts=postclose_facts_payload,
            fact_summary=fact_summary,
            news=news_payload,
            fallback_report_detail=fallback_report_detail,
        )
        report_detail = {
            **fallback_report_detail,
            **llm_report_detail,
        }
        llm_meta = llm_report_detail.get("llm_meta") or {}
        llm_status = {
            "enabled": True,
            "used": True,
            "provider": llm_meta.get("provider", "deepseek"),
            "model": llm_meta.get("model"),
            "message": "LLM report detail generated successfully.",
        }
    except Exception as exc:  # pragma: no cover
        errors.append(f"llm_report_detail: {exc}")

    payload = {
        "status": overall_status,
        "trade_date": resolved_trade_date,
        "data_sources": {
            "market": "Tushare daily + daily_basic",
            "news": news_payload.get("source_label") or "AKShare 新闻接口",
            "postclose_facts": [
                "Tushare moneyflow_ind_ths",
                "Tushare moneyflow_cnt_ths",
                "Tushare limit_list_d",
                "Tushare limit_cpt_list",
                "Tushare ths_hot",
            ],
        },
        "market": {
            "status": market_status,
            "message": market_payload.get("message", ""),
            "facts": facts,
            "summary_cards": _build_summary_cards(facts),
        },
        "postclose_facts": postclose_facts_payload,
        "fact_summary": fact_summary,
        "news": news_payload,
        "report_detail": report_detail,
        "llm_status": llm_status,
        "report_shell": {
            "headline": "待接 LLM 生成",
            "sections": [
                "一句话总收口",
                "盘型 / 环境",
                "资金流证据",
                "主线 / 次主线 / 风险边界 / 次日重点",
                "主线与轮动拆解",
                "市场情绪与连板结构",
                "原因拆解",
                "次日执行卡",
            ],
        },
        "errors": errors,
    }
    return _sanitize_payload(payload)
