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
    "rise_n_days": '{"days": N, "bounds": [min, max]}，表示近 N 日涨幅区间',
    "pullback_n_days": '{"days": N, "bounds": [min, max]}，表示近 N 日回撤区间',
    "ma_position": '"above_ma5_ma10" | "near_ma20"',
    "ma_breakout": '"breakout_ma20" | "breakout_ma60"',
    "new_high_low": '"high_20d" | "high_60d" | "low_20d"',
    "consecutive_up_down": '{"direction": "up/down", "min_days": x, "max_days": y}',
    "volume_expansion_shrink": '"volume_expand_2d" | "volume_shrink_2d"',
    "chip_concentration": "筹码集中度区间 [min, max]，越低代表筹码越集中",
    "winner_rate": "获利盘比例区间 [min, max]，单位%",
    "price_vs_chip": "现价相对筹码成本区间 [min, max]，单位%",
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
    "rise_n_days": "近 N 日涨幅",
    "pullback_n_days": "近 N 日回撤",
    "ma_position": "均线位置",
    "ma_breakout": "均线突破",
    "new_high_low": "新高 / 新低",
    "consecutive_up_down": "连续涨跌",
    "volume_expansion_shrink": "量能变化",
    "chip_concentration": "筹码集中度",
    "winner_rate": "获利盘比例",
    "price_vs_chip": "现价相对筹码成本",
}

ENUM_DISPLAY_LABELS = {
    "above_ma5_ma10": "站上 5 / 10 日均线",
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
        "note": "已识别为动量思路，映射到近 10 日涨幅、量比、换手率、成交额和 20 日新高。",
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
        "note": "已识别为反转思路，映射到回撤幅度、20 日均线附近、放量回升和均线突破。",
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
        "note": "已识别为回调思路，映射到近 10 日回撤、缩量整理和 20 日均线附近。",
    },
    {
        "id": "breakout",
        "label": "突破",
        "aliases": ["突破", "平台突破", "breakout", "出现突破信号"],
        "screen_depth": "full",
        "filters": {
            "ma_breakout": "breakout_ma20",
            "volume_expansion_shrink": "volume_expand_2d",
            "volume_ratio": [1.2, 4.5],
        },
        "expected_filters": ["ma_breakout", "volume_expansion_shrink", "volume_ratio"],
        "note": "已识别为突破思路，映射到 20 日均线突破和放量确认。",
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
]


def _build_system_prompt() -> str:
    return (
        "你是 A 股盘前选股策略解析助手。"
        "你的任务不是直接推荐股票，而是把用户的自然语言策略翻译成结构化筛选条件。"
        "你只能输出当前系统已支持的字段，不能编造不存在的指标。"
        "如果用户提到筹码结构、筹码干净、筹码稳定，优先映射到 chip_concentration、winner_rate、price_vs_chip。"
        "如果用户提到突破信号、放量突破、平台突破，优先映射到 ma_breakout、volume_expansion_shrink、volume_ratio。"
        "如果用户提到当前未接入能力，例如分时、盘口、龙虎榜席位细节，把它放进 unsupported_intents。"
        "输出必须是 JSON 对象，只包含这些顶层字段：screen_depth, market_scope, exclude_new_listing_90d, filters, notes, unsupported_intents。"
    )


def _build_user_prompt(query: str, current_payload: dict[str, Any]) -> str:
    payload = {
        "query": query,
        "current_payload": current_payload,
        "supported_filters": SUPPORTED_FILTER_HINTS,
        "rules": [
            "尽量保留用户当前已经填写的市场范围，除非用户明确要求修改。",
            "只返回需要覆盖的字段，不要把所有字段都重写。",
            "数值尽量给出合理可执行的宽区间，不要过于极端。",
            "反转、低吸、缩量回调后放量这类策略通常需要 full。",
            "notes 里用简短中文解释你为什么这么映射。",
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
    return _apply_strategy_tags(_match_strategy_tags(query))


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


def _llm_parse(query: str, current_payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_llm_settings()
    if not settings.enabled:
        raise DeepSeekAPIError("DeepSeek API key is not configured.")

    result = chat_completion_with_timeout(
        settings,
        system_prompt=_build_system_prompt(),
        user_prompt=_build_user_prompt(query, current_payload),
        response_format={"type": "json_object"},
        timeout_seconds=settings.timeout_seconds,
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


def _has_effective_filters(filters: dict[str, Any]) -> bool:
    for value in (filters or {}).values():
        if value not in (None, "", [], {}):
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


def _overlay_with_fallback(
    query: str,
    parsed_result: dict[str, Any],
    detected_strategy_tags: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    fallback_result = _apply_detected_tag_ids(detected_strategy_tags) if detected_strategy_tags else _fallback_parse(query)
    fallback_filters = {key: value for key, value in (fallback_result.get("filters") or {}).items() if value not in (None, "", {}, [])}

    used_overlay = False
    if fallback_filters:
        merged_filters = dict(parsed_result.get("filters") or {})
        before_effective = _has_effective_filters(merged_filters)
        merged_filters.update({key: value for key, value in fallback_filters.items() if merged_filters.get(key) in (None, "", {}, [])})
        parsed_result["filters"] = merged_filters
        after_effective = _has_effective_filters(merged_filters)
        used_overlay = after_effective and (not before_effective or merged_filters != dict(parsed_result.get("filters") or {}))

    _merge_strategy_metadata(parsed_result, fallback_result)

    if fallback_result.get("screen_depth") == "full":
        parsed_result["screen_depth"] = "full"

    if fallback_result.get("unsupported_intents"):
        parsed_result["unsupported_intents"] = list(
            {
                *list(parsed_result.get("unsupported_intents") or []),
                *list(fallback_result.get("unsupported_intents") or []),
            }
        )

    return parsed_result, used_overlay


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
    llm_status = {
        "enabled": False,
        "used": False,
        "provider": "deepseek",
        "model": None,
        "message": "LLM not configured. Using fallback parser.",
    }

    parsed_result: dict[str, Any] = {
        "screen_depth": normalized_current.get("screen_depth", "fast"),
        "filters": {},
        "notes": [],
        "unsupported_intents": [],
        "strategy_tags": [],
        "strategy_mapping": [],
    }

    llm_error: str | None = None
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
    except Exception as exc:  # pragma: no cover
        llm_error = str(exc)
        llm_status["message"] = f"Using fallback parser: {exc}"

    parsed_result, used_overlay = _overlay_with_fallback(clean_query, parsed_result, detected_strategy_tags)

    if used_overlay:
        parsed_result["notes"] = list(parsed_result.get("notes") or []) + ["已叠加规则兜底，确保核心策略关键词被映射到可执行条件。"]

    if not _has_effective_filters(parsed_result.get("filters") or {}):
        fallback_only = _apply_detected_tag_ids(detected_strategy_tags) if detected_strategy_tags else _fallback_parse(clean_query)
        if _has_effective_filters(fallback_only.get("filters") or {}):
            parsed_result = fallback_only
            if llm_error:
                llm_status["message"] = f"LLM unavailable, switched to fallback parser: {llm_error}"
            else:
                llm_status["message"] = "LLM returned no effective filters. Switched to fallback parser."

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
