from __future__ import annotations

import json
from typing import Any

try:
    from .deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from .llm_config import load_llm_settings
    from .premarket_shared import normalize_payload
except ImportError:
    from deepseek_provider import DeepSeekAPIError, chat_completion_with_timeout
    from llm_config import load_llm_settings
    from premarket_shared import normalize_payload


SUPPORTED_FILTER_HINTS = {
    "price_range": "股价区间 [min, max]，单位元",
    "total_market_cap": "总市值区间 [min, max]，单位元",
    "circulating_market_cap": "流通市值区间 [min, max]，单位元",
    "change_pct": "当日涨跌幅区间 [min, max]，单位%",
    "turnover_rate": "换手率区间 [min, max]，单位%",
    "amount": "成交额区间 [min, max]，单位元",
    "amplitude": "振幅区间 [min, max]，单位%",
    "volume_ratio": "量比区间 [min, max]",
    "rise_n_days": '{"days": 5或10, "bounds": [min, max]}，表示近N日涨幅',
    "pullback_n_days": '{"days": 10, "bounds": [min, max]}，表示近N日回撤',
    "ma_position": '"" | "above_ma5_ma10" | "near_ma20"',
    "ma_breakout": '"" | "breakout_ma20" | "breakout_ma60"',
    "new_high_low": '"" | "high_20d" | "high_60d" | "low_20d"',
    "consecutive_up_down": '{"direction": "up/down", "min_days": x, "max_days": y}',
    "volume_expansion_shrink": '"" | "volume_expand_2d" | "volume_shrink_2d"',
    "chip_concentration": "筹码集中度区间 [min, max]，单位%，越低代表筹码越集中",
    "winner_rate": "获利盘比例区间 [min, max]，单位%",
    "price_vs_chip": "现价相对筹码成本区间 [min, max]，单位%，负值表示现价低于平均筹码成本",
}

FILTER_DISPLAY_LABELS = {
    "price_range": "股价区间",
    "total_market_cap": "总市值",
    "circulating_market_cap": "流通市值",
    "change_pct": "涨跌幅",
    "turnover_rate": "换手率",
    "amount": "成交额",
    "amplitude": "振幅",
    "volume_ratio": "量比",
    "rise_n_days": "近N日涨幅",
    "pullback_n_days": "近N日回调",
    "ma_position": "均线位置",
    "ma_breakout": "均线突破",
    "new_high_low": "新高/新低",
    "consecutive_up_down": "连续涨跌",
    "volume_expansion_shrink": "量能变化",
    "chip_concentration": "筹码集中度",
    "winner_rate": "获利盘比例",
    "price_vs_chip": "现价相对筹码成本",
}

ENUM_DISPLAY_LABELS = {
    "above_ma5_ma10": "站上 5/10 日均线",
    "near_ma20": "贴近 20 日均线",
    "breakout_ma20": "突破 20 日均线",
    "breakout_ma60": "突破 60 日均线",
    "high_20d": "20 日新高",
    "high_60d": "60 日新高",
    "low_20d": "20 日新低",
    "volume_expand_2d": "连续放量 2 日及以上",
    "volume_shrink_2d": "连续缩量 2 日及以上",
}

STRATEGY_TAG_LIBRARY = [
    {
        "id": "momentum",
        "label": "动量",
        "aliases": ["动量", "momentum", "强趋势", "趋势强化"],
        "screen_depth": "full",
        "filters": {
            "rise_n_days": {"days": 10, "bounds": [8, 25]},
            "volume_ratio": [1.5, 4.0],
            "turnover_rate": [4, 18],
            "amount": [3e8, 1.2e10],
            "new_high_low": "high_20d",
        },
        "expected_filters": ["rise_n_days", "volume_ratio", "turnover_rate", "amount", "new_high_low"],
        "note": "已识别为动量思路，映射到近10日涨幅、量比、换手率、成交额和20日新高。",
    },
    {
        "id": "reversal",
        "label": "反转",
        "aliases": ["反转", "反弹", "低吸", "reversal", "mean reversion"],
        "screen_depth": "full",
        "filters": {
            "change_pct": [-4, 4],
            "pullback_n_days": {"days": 10, "bounds": [3, 15]},
            "ma_position": "near_ma20",
            "ma_breakout": "breakout_ma20",
            "volume_expansion_shrink": "volume_expand_2d",
            "volume_ratio": [1.2, 4.0],
        },
        "expected_filters": ["pullback_n_days", "ma_position", "ma_breakout", "volume_expansion_shrink", "volume_ratio"],
        "note": "已识别为反转思路，映射到回调幅度、20日均线附近、放量回升与均线突破。",
    },
    {
        "id": "pullback",
        "label": "回调",
        "aliases": ["回调", "回踩", "pullback", "缩量回调"],
        "screen_depth": "full",
        "filters": {
            "pullback_n_days": {"days": 10, "bounds": [2, 12]},
            "volume_expansion_shrink": "volume_shrink_2d",
            "ma_position": "near_ma20",
        },
        "expected_filters": ["pullback_n_days", "volume_expansion_shrink", "ma_position"],
        "note": "已识别为回调思路，映射到近10日回调、缩量整理和20日均线附近。",
    },
    {
        "id": "volume_expand",
        "label": "放量",
        "aliases": ["放量", "量能放大", "volume expansion", "放量突破"],
        "screen_depth": "full",
        "filters": {
            "volume_expansion_shrink": "volume_expand_2d",
            "volume_ratio": [1.5, 5.0],
        },
        "expected_filters": ["volume_expansion_shrink", "volume_ratio"],
        "note": "已识别为放量思路，映射到连续放量和量比放大。",
    },
    {
        "id": "volume_shrink",
        "label": "缩量",
        "aliases": ["缩量", "量能收缩", "volume shrink", "缩量整理"],
        "screen_depth": "full",
        "filters": {
            "volume_expansion_shrink": "volume_shrink_2d",
        },
        "expected_filters": ["volume_expansion_shrink"],
        "note": "已识别为缩量思路，映射到连续缩量。",
    },
    {
        "id": "breakout",
        "label": "突破",
        "aliases": ["突破", "平台突破", "breakout"],
        "screen_depth": "full",
        "filters": {
            "ma_breakout": "breakout_ma20",
        },
        "expected_filters": ["ma_breakout"],
        "note": "已识别为突破思路，映射到20日均线突破。",
    },
    {
        "id": "new_high",
        "label": "新高",
        "aliases": ["新高", "阶段新高", "high breakout", "new high"],
        "screen_depth": "full",
        "filters": {
            "new_high_low": "high_20d",
        },
        "expected_filters": ["new_high_low"],
        "note": "已识别为新高思路，映射到20日新高。",
    },
    {
        "id": "oversold",
        "label": "超跌",
        "aliases": ["超跌", "跌深反弹", "oversold"],
        "screen_depth": "full",
        "filters": {
            "change_pct": [-8, 2],
            "new_high_low": "low_20d",
            "pullback_n_days": {"days": 10, "bounds": [8, 20]},
        },
        "expected_filters": ["change_pct", "new_high_low", "pullback_n_days"],
        "note": "已识别为超跌反弹思路，映射到低位回调与20日新低附近。",
    },
    {
        "id": "strong_tape",
        "label": "强势",
        "aliases": ["连板", "强势", "主升", "trend leader"],
        "screen_depth": "full",
        "filters": {
            "consecutive_up_down": {"direction": "up", "min_days": 2, "max_days": 5},
        },
        "expected_filters": ["consecutive_up_down"],
        "note": "已识别为强势思路，映射到连续上涨天数。",
    },
    {
        "id": "chip_focus",
        "label": "筹码集中",
        "aliases": ["筹码", "筹码集中", "筹码结构", "筹码结构干净", "筹码干净", "筹码稳定", "chip"],
        "screen_depth": "full",
        "filters": {
            "chip_concentration": [0, 18],
            "winner_rate": [35, 80],
            "price_vs_chip": [-6, 6],
        },
        "expected_filters": ["chip_concentration", "winner_rate", "price_vs_chip"],
        "note": "已识别为筹码思路，映射到筹码集中度、获利盘比例和现价相对筹码成本。",
    },
    {
        "id": "winner_rate",
        "label": "获利盘",
        "aliases": ["获利盘", "套牢盘轻", "winner rate"],
        "screen_depth": "full",
        "filters": {
            "winner_rate": [35, 80],
        },
        "expected_filters": ["winner_rate"],
        "note": "已识别为获利盘思路，映射到获利盘比例区间。",
    },
    {
        "id": "chip_cost",
        "label": "成本附近",
        "aliases": ["成本附近", "回到成本", "筹码成本", "cost line"],
        "screen_depth": "full",
        "filters": {
            "price_vs_chip": [-4, 4],
        },
        "expected_filters": ["price_vs_chip"],
        "note": "已识别为成本回归思路，映射到现价相对筹码成本区间。",
    },
    {
        "id": "trend_acceleration",
        "label": "趋势加速",
        "aliases": ["趋势加速", "加速", "加速段", "accelerate"],
        "screen_depth": "full",
        "filters": {
            "rise_n_days": {"days": 10, "bounds": [12, 35]},
            "volume_ratio": [1.8, 5.0],
            "ma_breakout": "breakout_ma20",
            "new_high_low": "high_20d",
        },
        "expected_filters": ["rise_n_days", "volume_ratio", "ma_breakout", "new_high_low"],
        "note": "已识别为趋势加速思路，映射到更高的近10日涨幅、量比放大、20日均线突破与20日新高。",
    },
    {
        "id": "ma_bull",
        "label": "均线多头",
        "aliases": ["均线多头", "多头排列", "沿均线走强", "ma bull"],
        "screen_depth": "full",
        "filters": {
            "ma_position": "above_ma5_ma10",
            "rise_n_days": {"days": 5, "bounds": [3, 18]},
            "volume_ratio": [1.0, 3.5],
        },
        "expected_filters": ["ma_position", "rise_n_days", "volume_ratio"],
        "note": "已识别为均线多头思路，映射到站上5/10日均线、近5日上涨和温和放量。",
    },
    {
        "id": "platform_breakout",
        "label": "平台突破",
        "aliases": ["平台突破", "箱体突破", "突破平台", "platform breakout"],
        "screen_depth": "full",
        "filters": {
            "ma_breakout": "breakout_ma20",
            "volume_ratio": [1.5, 4.5],
            "amplitude": [3, 10],
        },
        "expected_filters": ["ma_breakout", "volume_ratio", "amplitude"],
        "note": "已识别为平台突破思路，映射到20日均线突破、量比放大和适中振幅。",
    },
    {
        "id": "weak_to_strong",
        "label": "弱转强",
        "aliases": ["弱转强", "转强", "分歧转强", "weak to strong"],
        "screen_depth": "full",
        "filters": {
            "change_pct": [-2, 5],
            "pullback_n_days": {"days": 10, "bounds": [2, 10]},
            "volume_ratio": [1.5, 4.5],
            "ma_breakout": "breakout_ma20",
        },
        "expected_filters": ["change_pct", "pullback_n_days", "volume_ratio", "ma_breakout"],
        "note": "已识别为弱转强思路，映射到适度回调后重新放量并尝试突破。",
    },
    {
        "id": "leader_return",
        "label": "龙头回流",
        "aliases": ["龙头回流", "核心回流", "主线回流", "leader return"],
        "screen_depth": "full",
        "filters": {
            "pullback_n_days": {"days": 10, "bounds": [2, 8]},
            "consecutive_up_down": {"direction": "up", "min_days": 2, "max_days": 5},
            "volume_ratio": [1.2, 3.8],
        },
        "expected_filters": ["pullback_n_days", "consecutive_up_down", "volume_ratio"],
        "note": "已识别为龙头回流思路，映射到核心强势股回调后的二次承接观察。",
    },
    {
        "id": "small_cap_elasticity",
        "label": "小票弹性",
        "aliases": ["小票弹性", "小市值弹性", "弹性票", "small cap"],
        "screen_depth": "fast",
        "filters": {
            "total_market_cap": [4e9, 2.5e10],
            "circulating_market_cap": [2e9, 1.5e10],
            "turnover_rate": [6, 22],
            "amount": [2e8, 5e9],
        },
        "expected_filters": ["total_market_cap", "circulating_market_cap", "turnover_rate", "amount"],
        "note": "已识别为小票弹性思路，映射到更小市值、更高换手和中等成交额。",
    },
]


def _build_system_prompt() -> str:
    return (
        "你是A股盘前选股策略解析助手。"
        "你的任务不是直接推荐股票，而是把用户的自然语言策略翻译成结构化筛选条件。"
        "你只能输出当前系统已经支持的字段，不能编造不存在的指标。"
        "对于筹码相关表达，默认优先映射到已支持的日级代理字段：chip_concentration、winner_rate、price_vs_chip。"
        "如果用户提到当前未接入的能力，比如分时、盘口、龙虎榜席位细节，你要把它放进 unsupported_intents。"
        "如果策略明显需要历史趋势判断，请把 screen_depth 设为 full。"
        "如果只是当日快筛，请把 screen_depth 设为 fast。"
        "输出必须是JSON对象，只能包含这些顶层字段："
        "screen_depth, market_scope, exclude_new_listing_90d, filters, notes, unsupported_intents。"
    )


def _build_user_prompt(query: str, current_payload: dict[str, Any]) -> str:
    payload = {
        "query": query,
        "current_payload": current_payload,
        "supported_filters": SUPPORTED_FILTER_HINTS,
        "rules": [
            "尽量保留用户当前已填写的市场范围，除非用户明确要求修改。",
            "只返回需要覆盖的字段，不要把所有字段都重写。",
            "数值尽量给出合理可执行的宽区间，不要过于极端。",
            "反转、低吸、缩量回调后放量这类策略通常需要full。",
            "如果用户提到筹码集中、套牢盘轻、获利盘适中、现价回到成本附近，可以优先使用 chip_concentration、winner_rate、price_vs_chip。",
            "如果用户说'筹码结构干净'、'筹码结构好'、'筹码稳定'，默认按已支持的筹码代理指标来映射，不要写成 unsupported_intents。",
            "notes里用简短中文解释你为什么这么映射。",
        ],
        "examples": [
            {
                "query": "给我一个反转策略",
                "result_hint": {
                    "screen_depth": "full",
                    "filters": {
                        "pullback_n_days": {"days": 10, "bounds": [3, 15]},
                        "ma_position": "near_ma20",
                        "ma_breakout": "breakout_ma20",
                        "volume_expansion_shrink": "volume_expand_2d",
                        "volume_ratio": [1.2, 4.0],
                    },
                },
            },
            {
                "query": "我想找突破新高且放量的票",
                "result_hint": {
                    "screen_depth": "full",
                    "filters": {
                        "new_high_low": "high_20d",
                        "ma_breakout": "breakout_ma20",
                        "volume_expansion_shrink": "volume_expand_2d",
                        "volume_ratio": [1.5, 5.0],
                    },
                },
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _match_strategy_tags(query: str) -> list[dict[str, Any]]:
    text = str(query or "").strip().lower()
    matched_tags: list[dict[str, Any]] = []
    for tag in STRATEGY_TAG_LIBRARY:
        aliases = [str(alias).strip().lower() for alias in tag.get("aliases", [])]
        if any(alias and alias in text for alias in aliases):
            matched_tags.append(tag)
    return matched_tags


def _apply_strategy_tags(matched_tags: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "screen_depth": "fast",
        "filters": {},
        "notes": [],
        "unsupported_intents": [],
        "strategy_tags": [],
        "strategy_mapping": [],
    }

    for tag in matched_tags:
        if tag.get("screen_depth") == "full":
            result["screen_depth"] = "full"
        result["filters"].update(tag.get("filters") or {})
        note = str(tag.get("note") or "").strip()
        if note:
            result["notes"].append(note)
        result["strategy_tags"].append({"id": tag.get("id"), "label": tag.get("label")})
        result["strategy_mapping"].append(
            {
                "tag_id": tag.get("id"),
                "tag_label": tag.get("label"),
                "mapped_filters": list(tag.get("expected_filters") or []),
            }
        )
    return result


def _apply_detected_tag_ids(tag_ids: list[str] | None) -> dict[str, Any]:
    clean_ids = {str(item).strip() for item in (tag_ids or []) if str(item).strip()}
    matched_tags = [tag for tag in STRATEGY_TAG_LIBRARY if str(tag.get("id")) in clean_ids]
    return _apply_strategy_tags(matched_tags)


def _fallback_parse(query: str) -> dict[str, Any]:
    matched_tags = _match_strategy_tags(query)
    return _apply_strategy_tags(matched_tags)


def _looks_garbled(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    question_mark_ratio = clean.count("?") / max(len(clean), 1)
    ascii_ratio = sum(1 for char in clean if ord(char) < 128) / max(len(clean), 1)
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in clean)
    if question_mark_ratio >= 0.2:
        return True
    if ascii_ratio > 0.95 and not has_cjk:
        return True
    return False


def _sanitize_llm_result(parsed: dict[str, Any]) -> dict[str, Any]:
    raw_notes = parsed.get("notes")
    if isinstance(raw_notes, str):
        note_list = [raw_notes.strip()] if raw_notes.strip() else []
    elif isinstance(raw_notes, list):
        note_list = [str(item).strip() for item in raw_notes if str(item).strip()]
    else:
        note_list = []

    raw_unsupported = parsed.get("unsupported_intents")
    if isinstance(raw_unsupported, str):
        unsupported_list = [raw_unsupported.strip()] if raw_unsupported.strip() else []
    elif isinstance(raw_unsupported, list):
        unsupported_list = [str(item).strip() for item in raw_unsupported if str(item).strip()]
    else:
        unsupported_list = []

    filtered_unsupported: list[str] = []
    for item in unsupported_list:
        lowered = item.lower()
        if "筹码结构" in item or "筹码分布" in item or "chip" in lowered:
            continue
        filtered_unsupported.append(item)
    unsupported_list = filtered_unsupported

    result: dict[str, Any] = {
        "screen_depth": parsed.get("screen_depth") if parsed.get("screen_depth") in {"fast", "full"} else "fast",
        "filters": parsed.get("filters") if isinstance(parsed.get("filters"), dict) else {},
        "notes": note_list,
        "unsupported_intents": unsupported_list,
        "strategy_tags": parsed.get("strategy_tags") if isinstance(parsed.get("strategy_tags"), list) else [],
        "strategy_mapping": parsed.get("strategy_mapping") if isinstance(parsed.get("strategy_mapping"), list) else [],
    }

    market_scope = str(parsed.get("market_scope") or "").strip()
    if market_scope:
        result["market_scope"] = market_scope
    if "exclude_new_listing_90d" in parsed:
        result["exclude_new_listing_90d"] = bool(parsed.get("exclude_new_listing_90d"))
    return result


def _needs_rule_overlay(query: str, parsed_result: dict[str, Any]) -> bool:
    filters = parsed_result.get("filters") or {}
    notes_text = " ".join(parsed_result.get("notes") or [])
    matched_tags = _match_strategy_tags(query)
    for tag in matched_tags:
        expected_filters = list(tag.get("expected_filters") or [])
        if expected_filters and not any(filters.get(filter_name) not in (None, "", {}, []) for filter_name in expected_filters):
            return True
    if "query为空" in notes_text or "未提出新的策略描述" in notes_text:
        return True
    if len(str(query or "").strip()) >= 6 and len(filters) <= 2:
        return True
    return False


def _merge_strategy_metadata(primary: dict[str, Any], overlay: dict[str, Any]) -> None:
    primary_tags = list(primary.get("strategy_tags") or [])
    overlay_tags = list(overlay.get("strategy_tags") or [])
    seen_tag_ids = {item.get("id") for item in primary_tags if isinstance(item, dict)}
    for item in overlay_tags:
        if isinstance(item, dict) and item.get("id") not in seen_tag_ids:
            primary_tags.append(item)
            seen_tag_ids.add(item.get("id"))
    primary["strategy_tags"] = primary_tags

    primary_mapping = list(primary.get("strategy_mapping") or [])
    overlay_mapping = list(overlay.get("strategy_mapping") or [])
    seen_mapping_ids = {item.get("tag_id") for item in primary_mapping if isinstance(item, dict)}
    for item in overlay_mapping:
        if isinstance(item, dict) and item.get("tag_id") not in seen_mapping_ids:
            primary_mapping.append(item)
            seen_mapping_ids.add(item.get("tag_id"))
    primary["strategy_mapping"] = primary_mapping


def _llm_parse(query: str, current_payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_llm_settings()
    if not settings.enabled:
        raise DeepSeekAPIError("DeepSeek API key is not configured.")

    result = chat_completion_with_timeout(
        settings,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_user_prompt(query, current_payload),
        response_format={"type": "json_object"},
        timeout_seconds=min(settings.timeout_seconds, 24.0),
    )
    parsed = json.loads(result["content"])
    if not isinstance(parsed, dict):
        raise DeepSeekAPIError("Strategy parser output is not a JSON object.")
    return _sanitize_llm_result(parsed)


def _merge_strategy_result(current_payload: dict[str, Any], parsed_result: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current_payload)
    merged_filters = dict(current_payload.get("filters") or {})
    merged_filters.update(parsed_result.get("filters") or {})
    merged["filters"] = merged_filters

    for key in ("screen_depth", "market_scope", "exclude_new_listing_90d"):
        if key in parsed_result:
            merged[key] = parsed_result[key]
    return normalize_payload(merged)


def _format_quant_condition(filter_name: str, value: Any) -> str | None:
    if value in (None, "", {}, []):
        return None

    label = FILTER_DISPLAY_LABELS.get(filter_name, filter_name)

    if isinstance(value, list) and len(value) == 2:
        lower, upper = value
        if filter_name in {"total_market_cap", "circulating_market_cap", "amount"}:
            return f"{label}: {lower / 1e8:.1f} - {upper / 1e8:.1f} 亿元"
        if filter_name == "price_range":
            return f"{label}: {lower:g} - {upper:g} 元"
        if filter_name == "volume_ratio":
            return f"{label}: {lower:g} - {upper:g}"
        return f"{label}: {lower:g}% - {upper:g}%"

    if isinstance(value, dict) and "bounds" in value:
        bounds = value.get("bounds") or [None, None]
        days = value.get("days")
        if bounds[0] is None or bounds[1] is None or not days:
            return None
        return f"{label}: 近 {int(days)} 日 {bounds[0]:g}% - {bounds[1]:g}%"

    if isinstance(value, dict) and "direction" in value:
        direction = "连涨" if value.get("direction") == "up" else "连跌"
        min_days = value.get("min_days")
        max_days = value.get("max_days")
        if min_days is None or max_days is None:
            return None
        return f"{label}: {direction} {int(min_days)} - {int(max_days)} 天"

    return f"{label}: {ENUM_DISPLAY_LABELS.get(str(value), value)}"


def _build_quantified_conditions(merged_payload: dict[str, Any]) -> list[str]:
    filters = merged_payload.get("filters") or {}
    ordered_filter_names = [
        "price_range",
        "total_market_cap",
        "circulating_market_cap",
        "change_pct",
        "turnover_rate",
        "amount",
        "amplitude",
        "volume_ratio",
        "rise_n_days",
        "pullback_n_days",
        "ma_position",
        "ma_breakout",
        "new_high_low",
        "consecutive_up_down",
        "volume_expansion_shrink",
        "chip_concentration",
        "winner_rate",
        "price_vs_chip",
    ]

    rows: list[str] = []
    for filter_name in ordered_filter_names:
        text = _format_quant_condition(filter_name, filters.get(filter_name))
        if text:
            rows.append(text)
    return rows


def _build_strategy_mapping_summary(strategy_mapping: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for item in strategy_mapping or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("tag_label") or item.get("tag_id") or "").strip()
        mapped_filters = [FILTER_DISPLAY_LABELS.get(name, name) for name in item.get("mapped_filters") or []]
        if label and mapped_filters:
            rows.append(f"{label} -> {' / '.join(mapped_filters)}")
    return rows


def parse_strategy_to_payload(
    query: str,
    current_payload: dict[str, Any] | None = None,
    detected_strategy_tags: list[str] | None = None,
) -> dict[str, Any]:
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("Strategy query is empty.")

    normalized_current = normalize_payload(current_payload or {})
    parsed_result: dict[str, Any]
    llm_status = {
        "enabled": False,
        "used": False,
        "provider": "deepseek",
        "model": None,
        "message": "LLM not configured. Using fallback parser.",
    }

    if _looks_garbled(clean_query):
        parsed_result = _apply_detected_tag_ids(detected_strategy_tags) if detected_strategy_tags else _fallback_parse(clean_query)
        llm_status["message"] = "Detected garbled query. Using fallback parser."
        merged_payload = _merge_strategy_result(normalized_current, parsed_result)
        return {
            "status": "ok",
            "query": clean_query,
            "parsed_strategy": parsed_result,
            "merged_payload": merged_payload,
            "quantified_conditions": _build_quantified_conditions(merged_payload),
            "strategy_mapping_summary": _build_strategy_mapping_summary(parsed_result.get("strategy_mapping") or []),
            "llm_status": llm_status,
        }

    try:
        parsed_result = _llm_parse(clean_query, normalized_current)
        settings = load_llm_settings()
        llm_status = {
            "enabled": True,
            "used": True,
            "provider": settings.provider,
            "model": settings.model,
            "message": "LLM strategy parser generated successfully.",
        }
        if _needs_rule_overlay(clean_query, parsed_result):
            fallback_result = _apply_detected_tag_ids(detected_strategy_tags) if detected_strategy_tags else _fallback_parse(clean_query)
            merged_filters = dict(parsed_result.get("filters") or {})
            merged_filters.update({key: value for key, value in (fallback_result.get("filters") or {}).items() if value not in (None, "", {}, [])})
            parsed_result["filters"] = merged_filters
            _merge_strategy_metadata(parsed_result, fallback_result)
            parsed_result["notes"] = list(parsed_result.get("notes") or []) + ["已叠加规则兜底，确保核心策略关键词被映射到可执行条件。"]
            parsed_result["unsupported_intents"] = list(
                {
                    *list(parsed_result.get("unsupported_intents") or []),
                    *list(fallback_result.get("unsupported_intents") or []),
                }
            )
            if fallback_result.get("screen_depth") == "full":
                parsed_result["screen_depth"] = "full"
    except Exception as exc:  # pragma: no cover
        parsed_result = _apply_detected_tag_ids(detected_strategy_tags) if detected_strategy_tags else _fallback_parse(clean_query)
        llm_status["message"] = f"Using fallback parser: {exc}"

    merged_payload = _merge_strategy_result(normalized_current, parsed_result)
    return {
        "status": "ok",
        "query": clean_query,
        "parsed_strategy": parsed_result,
        "merged_payload": merged_payload,
        "quantified_conditions": _build_quantified_conditions(merged_payload),
        "strategy_mapping_summary": _build_strategy_mapping_summary(parsed_result.get("strategy_mapping") or []),
        "llm_status": llm_status,
    }
