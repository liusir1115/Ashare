from __future__ import annotations

from copy import deepcopy
from typing import Any

try:
    from .backtest_service import run_backtest
    from .premarket_strategy_llm_service import parse_strategy_to_payload
    from .premarket_shared import normalize_payload
except ImportError:
    from backtest_service import run_backtest
    from premarket_strategy_llm_service import parse_strategy_to_payload
    from premarket_shared import normalize_payload


def _clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)


def _widen_numeric_range(bounds: list[float], factor: float = 0.2) -> list[float]:
    lower, upper = float(bounds[0]), float(bounds[1])
    span = upper - lower
    if span == 0:
        span = max(abs(lower), 1.0) * factor
    padding = span * factor
    return [lower - padding, upper + padding]


def _tighten_numeric_range(bounds: list[float], factor: float = 0.2) -> list[float]:
    lower, upper = float(bounds[0]), float(bounds[1])
    span = upper - lower
    if span <= 0:
        return [lower, upper]
    padding = span * factor
    new_lower = lower + padding
    new_upper = upper - padding
    if new_lower >= new_upper:
        return [lower, upper]
    return [new_lower, new_upper]


def _mutate_filters(filters: dict[str, Any], mode: str) -> dict[str, Any]:
    mutated = deepcopy(filters)
    for key, value in list(mutated.items()):
        if isinstance(value, list) and len(value) == 2:
            if mode == "loose":
                mutated[key] = _widen_numeric_range(value)
            elif mode == "strict":
                mutated[key] = _tighten_numeric_range(value)
        elif isinstance(value, dict) and "bounds" in value and isinstance(value.get("bounds"), list) and len(value["bounds"]) == 2:
            current_bounds = value["bounds"]
            value = deepcopy(value)
            if mode == "loose":
                value["bounds"] = _widen_numeric_range(current_bounds)
            elif mode == "strict":
                value["bounds"] = _tighten_numeric_range(current_bounds)
            mutated[key] = value
    return mutated


def _build_variant_payloads(base_payload: dict[str, Any]) -> list[dict[str, Any]]:
    base_filters = deepcopy(base_payload.get("filters") or {})

    base_variant = normalize_payload(_clone_payload(base_payload))

    loose_variant = normalize_payload(
        {
            **_clone_payload(base_payload),
            "filters": _mutate_filters(base_filters, "loose"),
        }
    )

    strict_variant = normalize_payload(
        {
            **_clone_payload(base_payload),
            "filters": _mutate_filters(base_filters, "strict"),
        }
    )

    return [
        {
            "id": "base",
            "label": "基准版",
            "description": "按当前自然语言策略直接翻译后的量化条件执行。",
            "screen_payload": base_variant,
        },
        {
            "id": "loose",
            "label": "放宽版",
            "description": "自动适度放宽区间约束，优先观察样本量和稳定性是否提升。",
            "screen_payload": loose_variant,
        },
        {
            "id": "strict",
            "label": "收紧版",
            "description": "自动适度收紧区间约束，优先观察收益质量是否提升。",
            "screen_payload": strict_variant,
        },
    ]


def compare_backtest_strategies(
    query: str,
    current_payload: dict[str, Any] | None = None,
    history_years: int = 3,
    holding_days: int = 3,
    top_n: int = 10,
    execution_mode: str = "fast",
) -> dict[str, Any]:
    current_payload = normalize_payload(current_payload or {})
    parsed = parse_strategy_to_payload(query, current_payload=current_payload, detected_strategy_tags=[])
    merged_payload = normalize_payload(parsed.get("merged_payload") or current_payload)
    variants = _build_variant_payloads(merged_payload)

    results: list[dict[str, Any]] = []
    for variant in variants:
        payload = {
            "screen_payload": variant["screen_payload"],
            "history_years": history_years,
            "holding_days": holding_days,
            "top_n": top_n,
            "execution_mode": execution_mode,
            "adj_type": "qfq",
        }
        run_result = run_backtest(payload)
        results.append(
            {
                "variant_id": variant["id"],
                "label": variant["label"],
                "description": variant["description"],
                "screen_payload": variant["screen_payload"],
                "summary": run_result.get("summary") or {},
                "warnings": run_result.get("warnings") or [],
                "debug": run_result.get("debug") or {},
                "trade_samples": run_result.get("trade_samples") or [],
                "yearly_returns": run_result.get("yearly_returns") or [],
            }
        )

    ranked = sorted(
        results,
        key=lambda item: (
            float((item.get("summary") or {}).get("cumulative_return_pct") or 0),
            -float((item.get("summary") or {}).get("max_drawdown_pct") or 0),
            float((item.get("summary") or {}).get("trade_count") or 0),
        ),
        reverse=True,
    )

    return {
        "status": "ok",
        "query": query,
        "execution_mode": execution_mode,
        "history_years": history_years,
        "holding_days": holding_days,
        "top_n": top_n,
        "parsed_strategy": parsed,
        "comparison": ranked,
        "recommendation": ranked[0] if ranked else None,
    }
