from __future__ import annotations

import json
from typing import Any


def _pick_titles(items: list[dict[str, Any]], key: str, limit: int = 3) -> list[str]:
    titles: list[str] = []
    for item in items[:limit]:
        value = str(item.get(key) or "").strip()
        if value:
            titles.append(value)
    return titles


def _normalize_hot_concepts(items: list[dict[str, Any]], limit: int = 5) -> list[str]:
    concepts: list[str] = []
    seen: set[str] = set()

    for item in items:
        raw_value = item.get("concept")
        if raw_value in (None, ""):
            continue

        values: list[str]
        if isinstance(raw_value, str) and raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                parsed = json.loads(raw_value)
                values = [str(value).strip() for value in parsed if str(value).strip()]
            except json.JSONDecodeError:
                values = [raw_value.strip()]
        else:
            values = [str(raw_value).strip()]

        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            concepts.append(value)
            if len(concepts) >= limit:
                return concepts

    return concepts


def build_postclose_fact_summary(facts_payload: dict[str, Any]) -> dict[str, Any]:
    industry_inflow = facts_payload.get("moneyflow_ind", {}).get("top_inflow", [])
    concept_inflow = facts_payload.get("moneyflow_concept", {}).get("top_inflow", [])
    limit_items = facts_payload.get("limit_concepts", {}).get("items", [])
    hot_items = facts_payload.get("hotspots", {}).get("top_ranked", [])
    limit_summary = facts_payload.get("limit_structure", {}).get("summary", {})

    mainline_candidates = _pick_titles(industry_inflow, "industry")
    concept_candidates = _pick_titles(concept_inflow, "concept_name")
    hot_topics = _normalize_hot_concepts(hot_items)

    return {
        "mainline_candidates": mainline_candidates,
        "concept_candidates": concept_candidates,
        "hot_topics": hot_topics,
        "emotion_snapshot": {
            "limit_up_count": int(limit_summary.get("limit_up_count", 0)),
            "highest_board": int(limit_summary.get("highest_board", 0)),
            "limit_focus": _pick_titles(limit_items, "name"),
        },
    }
