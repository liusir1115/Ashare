from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "result" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PRIORITY_KEYWORD_WEIGHTS = {
    "AI应用": 6.0,
    "人工智能": 6.0,
    "机器人": 5.5,
    "液冷服务器": 5.5,
    "AI PC": 5.0,
    "算力": 5.0,
    "芯片概念": 5.0,
    "存储芯片": 4.6,
    "先进封装": 4.5,
    "半导体": 4.4,
    "创投": 4.2,
    "小米概念": 4.0,
    "智能穿戴": 3.8,
    "新型城镇化": 4.4,
    "装配式建筑": 4.2,
    "并购重组": 4.0,
    "回购增持": 3.5,
}

NEWS_KEYWORD_GROUPS = {
    "AI应用": ["ai", "kimi", "大模型", "智能体", "人工智能"],
    "机器人": ["机器人", "人形机器人"],
    "液冷服务器": ["液冷", "服务器"],
    "AI PC": ["ai pc", "aipc"],
    "算力": ["算力", "智算", "gpu"],
    "芯片概念": ["芯片", "晶圆", "半导体"],
    "并购重组": ["并购", "重组", "收购"],
    "回购增持": ["回购", "增持"],
    "小米概念": ["小米"],
    "创投": ["创投", "投资"],
    "智能穿戴": ["智能穿戴", "可穿戴", "手环", "手表"],
}

GENERIC_DRIVER_KEYWORDS = [
    "A股",
    "同花顺",
    "昨日",
    "近期",
    "最近",
    "情绪指数",
    "表现",
    "龙虎榜",
    "高贝塔",
    "新高",
    "减持计划",
]


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    digits = "".join(char for char in text if char.isdigit())
    return digits[-6:] if len(digits) >= 6 else text


def _to_ak_symbol(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    if normalized.startswith(("0", "1", "2", "3")):
        return f"SZ{normalized}"
    return f"SH{normalized}"


def _load_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def _concept_match(left: str, right: str) -> bool:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False
    return left_text == right_text or left_text in right_text or right_text in left_text


def _is_generic_driver_label(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if text.endswith("(A股)"):
        return True
    return any(keyword in text for keyword in GENERIC_DRIVER_KEYWORDS)


def _fetch_cached_frame(cache_key: str, fetcher) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"{cache_key}.json"
    cached = _load_cache(cache_path)
    if cached and isinstance(cached.get("rows"), list):
        return pd.DataFrame(cached["rows"])
    try:
        df = fetcher()
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    _save_cache(cache_path, {"rows": df.to_dict(orient="records")})
    return df.copy()


def fetch_stock_hot_keywords(symbol: str) -> pd.DataFrame:
    ak_symbol = _to_ak_symbol(symbol)
    return _fetch_cached_frame(
        f"stock_hot_keyword_{ak_symbol}",
        lambda: ak.stock_hot_keyword_em(symbol=ak_symbol),
    )


def fetch_stock_related_hot(symbol: str) -> pd.DataFrame:
    ak_symbol = _to_ak_symbol(symbol)
    return _fetch_cached_frame(
        f"stock_hot_related_{ak_symbol}",
        lambda: ak.stock_hot_rank_relate_em(symbol=ak_symbol),
    )


def fetch_stock_news(symbol: str) -> pd.DataFrame:
    normalized = _normalize_symbol(symbol)
    return _fetch_cached_frame(
        f"stock_news_{normalized}",
        lambda: ak.stock_news_em(symbol=normalized),
    )


def fetch_stock_hot_rank_realtime(symbol: str) -> pd.DataFrame:
    ak_symbol = _to_ak_symbol(symbol)
    return _fetch_cached_frame(
        f"stock_hot_rank_realtime_{ak_symbol}",
        lambda: ak.stock_hot_rank_detail_realtime_em(symbol=ak_symbol),
    )


def _extract_news_keywords(news_df: pd.DataFrame) -> list[str]:
    if news_df is None or news_df.empty:
        return []

    texts: list[str] = []
    for _, row in news_df.head(8).iterrows():
        texts.append(str(row.get("新闻标题") or "").strip())
        texts.append(str(row.get("新闻内容") or "")[:240].strip())
    merged = " ".join(texts).lower()

    matched: list[str] = []
    for concept_name, keywords in NEWS_KEYWORD_GROUPS.items():
        if any(keyword in merged for keyword in keywords):
            matched.append(concept_name)
    return matched


def _score_candidate(
    *,
    candidate: str,
    keyword_scores: dict[str, float],
    concept_fact: dict[str, Any],
    market_topics: list[str],
    news_keywords: list[str],
    related_concepts: list[str],
) -> float:
    score = 0.0

    if candidate in keyword_scores:
        score += min(keyword_scores[candidate] / 18.0, 8.0)
    if any(_concept_match(candidate, topic) for topic in market_topics):
        score += 7.0
    if candidate in (concept_fact.get("hotspot_concepts") or []):
        score += 5.0
    if candidate in (concept_fact.get("market_overlap") or []):
        score += 4.5
    if any(_concept_match(candidate, keyword) for keyword in news_keywords):
        score += 4.5
    if (
        any(_concept_match(candidate, related) for related in related_concepts)
        and (
            candidate in keyword_scores
            or any(_concept_match(candidate, topic) for topic in market_topics)
            or any(_concept_match(candidate, keyword) for keyword in news_keywords)
        )
    ):
        score += 3.5
    if candidate in (concept_fact.get("board_memberships") or []):
        score += 2.0
    if candidate in PRIORITY_KEYWORD_WEIGHTS:
        score += PRIORITY_KEYWORD_WEIGHTS[candidate]

    if _is_generic_driver_label(candidate):
        score -= 6.0

    return score


def build_stock_driver_analysis(
    *,
    symbol: str,
    name: str,
    concept_fact: dict[str, Any],
    fact_summary: dict[str, Any],
    hotspot_symbol_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hot_keyword_df = fetch_stock_hot_keywords(symbol)
    related_df = fetch_stock_related_hot(symbol)
    news_df = fetch_stock_news(symbol)
    rank_df = fetch_stock_hot_rank_realtime(symbol)

    market_topics = _dedupe_texts(
        [str(item).strip() for item in fact_summary.get("concept_candidates", [])]
        + [str(item).strip() for item in fact_summary.get("hot_topics", [])]
        + [str(item).strip() for item in fact_summary.get("mainline_candidates", [])]
    )

    keyword_scores: dict[str, float] = {}
    if hot_keyword_df is not None and not hot_keyword_df.empty:
        for _, row in hot_keyword_df.iterrows():
            concept_name = str(row.get("概念名称") or "").strip()
            if not concept_name or _is_generic_driver_label(concept_name):
                continue
            try:
                heat_value = float(row.get("热度") or 0)
            except (TypeError, ValueError):
                heat_value = 0.0
            keyword_scores[concept_name] = heat_value

    related_lines: list[str] = []
    related_concepts: list[str] = []
    if related_df is not None and not related_df.empty:
        for _, row in related_df.head(6).iterrows():
            related_code = _normalize_symbol(row.get("相关股票代码"))
            if not related_code:
                continue
            related_fact = hotspot_symbol_lookup.get(related_code, {})
            related_name = str(related_fact.get("name") or related_code).strip()
            concepts = [item for item in (related_fact.get("concepts") or []) if not _is_generic_driver_label(item)]
            related_concepts.extend(concepts)
            label = related_name
            if concepts:
                label = f"{related_name} {' / '.join(concepts[:2])}"
            related_lines.append(label)

    news_keywords = _extract_news_keywords(news_df)
    related_concepts = _dedupe_texts(related_concepts)

    concept_candidates = _dedupe_texts(
        [item for item in keyword_scores.keys()]
        + [item for item in (concept_fact.get("market_overlap") or [])]
        + [item for item in (concept_fact.get("hotspot_concepts") or [])]
        + [item for item in (concept_fact.get("board_memberships") or []) if not _is_generic_driver_label(item)]
        + news_keywords
    )

    scored: list[tuple[str, float]] = []
    for candidate in concept_candidates:
        score = _score_candidate(
            candidate=candidate,
            keyword_scores=keyword_scores,
            concept_fact=concept_fact,
            market_topics=market_topics,
            news_keywords=news_keywords,
            related_concepts=related_concepts,
        )
        if score > 0:
            scored.append((candidate, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    driver_candidates = [name for name, _ in scored[:4]]

    evidence_lines = list(concept_fact.get("driver_evidence") or [])
    if keyword_scores:
        top_keywords = sorted(keyword_scores.items(), key=lambda item: item[1], reverse=True)[:4]
        evidence_lines.append(
            "个股热词热度："
            + " / ".join([f"{keyword}({int(score)})" for keyword, score in top_keywords])
        )
    if related_lines:
        evidence_lines.append("关联热股：" + "；".join(related_lines[:4]))
    if news_keywords:
        evidence_lines.append("新闻关键词：" + " / ".join(news_keywords[:4]))
    if news_df is not None and not news_df.empty:
        first_news = news_df.iloc[0]
        news_title = str(first_news.get("新闻标题") or "").strip()
        news_source = str(first_news.get("文章来源") or "").strip()
        if news_title:
            evidence_lines.append(f"个股新闻：{news_title}（{news_source or '新闻源'}）")
    if rank_df is not None and not rank_df.empty:
        latest_rank = rank_df.iloc[-1].get("排名")
        if latest_rank not in (None, ""):
            evidence_lines.append(f"实时热度排名：第 {latest_rank} 名")

    return {
        "symbol": symbol,
        "name": name,
        "driver_candidates": driver_candidates or list(concept_fact.get("driver_candidates") or [])[:4],
        "driver_evidence": _dedupe_texts(evidence_lines),
        "keyword_concepts": sorted(keyword_scores.items(), key=lambda item: item[1], reverse=True),
        "news_keywords": news_keywords,
        "related_concepts": related_concepts,
    }
