from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

import akshare as ak
import pandas as pd


NEWS_CACHE_TTL_SECONDS = 180
NEWS_CACHE: dict[str, Any] = {"expires_at": 0.0, "brief_date": None, "data": None}
HIGH_PRIORITY_KEYWORDS = [
    "A股",
    "沪指",
    "深成指",
    "创业板",
    "科创板",
    "北交所",
    "证监会",
    "央行",
    "国常会",
    "半导体",
    "算力",
    "AI",
    "人工智能",
    "消费电子",
    "证券",
    "芯片",
    "机器人",
    "新能源",
    "光伏",
    "储能",
    "军工",
    "CPO",
    "液冷",
    "并购",
    "增持",
    "回购",
]


def format_datetime_text(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _split_long_summary(summary: str) -> list[str]:
    text = _normalize_text(summary)
    if not text:
        return []
    text = re.sub(r"^【|】$", "", text)
    parts = re.split(r"[；;。]\s*", text)
    clean = [part.strip("、，, ") for part in parts if part.strip()]
    return clean


def _score_a_share_relevance(title: str, summary: str) -> int:
    text = f"{_normalize_text(title)} {_normalize_text(summary)}"
    score = 0
    for keyword in HIGH_PRIORITY_KEYWORDS:
        if keyword.lower() in text.lower():
            score += 2
    if "中国" in text:
        score += 1
    if "美股" in text or "英国" in text or "卡塔尔" in text or "原油" in text:
        score -= 1
    return score


def build_brief_item(title: str, summary: str, published_at: str, source: str, url: str | None = None) -> dict[str, str]:
    item = {
        "title": _normalize_text(title),
        "summary": _normalize_text(summary),
        "published_at": _normalize_text(published_at),
        "source": source,
    }
    if url:
        item["url"] = url
    return item


def _safe_head(df: pd.DataFrame | None, limit: int = 6) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df.head(limit).copy()


def fetch_eastmoney_global_brief(today_text: str) -> dict[str, Any] | None:
    news_df = ak.stock_info_global_em()
    if news_df is None or news_df.empty:
        return None

    working_df = news_df.copy()
    working_df["发布时间"] = pd.to_datetime(working_df["发布时间"], errors="coerce")
    working_df = working_df.dropna(subset=["发布时间"])
    working_df["date_text"] = working_df["发布时间"].dt.strftime("%Y-%m-%d")
    today_df = working_df[working_df["date_text"] == today_text].copy()
    if today_df.empty:
        today_df = working_df.copy()

    today_df["a_share_score"] = today_df.apply(
        lambda row: _score_a_share_relevance(row.get("标题", ""), row.get("摘要", "")),
        axis=1,
    )
    today_df = today_df.sort_values(["a_share_score", "发布时间"], ascending=[False, False])
    items = [
        build_brief_item(
            title=row.get("标题", "财经快讯"),
            summary=row.get("摘要", ""),
            published_at=format_datetime_text(row.get("发布时间")),
            source="东方财富财经快讯",
            url=_normalize_text(row.get("链接")) or None,
        )
        for _, row in _safe_head(today_df, 8).iterrows()
        if _normalize_text(row.get("标题")) or _normalize_text(row.get("摘要"))
    ]
    if not items:
        return None

    return {
        "status": "ok",
        "brief_date": today_text,
        "source": "stock_info_global_em",
        "source_label": "AKShare 东方财富财经快讯",
        "updated_at": items[0]["published_at"],
        "items": items,
    }


def fetch_caixin_market_brief() -> dict[str, Any] | None:
    news_df = ak.stock_news_main_cx()
    if news_df is None or news_df.empty:
        return None

    working_df = news_df.copy()
    today_text = datetime.now().strftime("%Y-%m-%d")
    items = []
    for _, row in _safe_head(working_df, 6).iterrows():
        tag = _normalize_text(row.get("tag") or "财新要闻")
        summary = _normalize_text(row.get("summary"))
        if not summary:
            continue
        items.append(
            build_brief_item(
                title=tag,
                summary=summary,
                published_at=today_text,
                source="财新市场要闻",
                url=_normalize_text(row.get("url")) or None,
            )
        )
    if not items:
        return None

    return {
        "status": "ok",
        "brief_date": today_text,
        "source": "stock_news_main_cx",
        "source_label": "AKShare 财新市场要闻",
        "updated_at": items[0]["published_at"],
        "items": items,
    }


def fetch_cls_focus_brief(today_text: str) -> dict[str, Any] | None:
    cls_df = ak.stock_info_global_cls(symbol="重点")
    if cls_df is None or cls_df.empty:
        return None

    working_df = cls_df.copy()
    working_df["发布日期"] = working_df["发布日期"].astype(str)
    working_df["发布时间"] = working_df["发布时间"].astype(str)
    today_df = working_df[working_df["发布日期"] == today_text].copy()
    if today_df.empty:
        return None

    today_df["_sort_key"] = pd.to_datetime(
        today_df["发布日期"] + " " + today_df["发布时间"],
        errors="coerce",
    )
    today_df = today_df.sort_values("_sort_key", ascending=False)
    items = [
        build_brief_item(
            title=row.get("标题", "财联社重点电报"),
            summary=row.get("内容", ""),
            published_at=f"{row['发布日期']} {row['发布时间']}",
            source="财联社重点电报",
        )
        for _, row in _safe_head(today_df, 6).iterrows()
        if _normalize_text(row.get("标题")) or _normalize_text(row.get("内容"))
    ]
    if not items:
        return None

    return {
        "status": "ok",
        "brief_date": today_text,
        "source": "stock_info_global_cls",
        "source_label": "AKShare 财联社重点电报",
        "updated_at": items[0]["published_at"],
        "items": items,
    }


def _merge_news_briefs(briefs: list[dict[str, Any]], today_text: str) -> dict[str, Any] | None:
    collected: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    source_labels: list[str] = []
    updated_at = ""

    for brief in briefs:
        if not brief:
            continue
        source_label = _normalize_text(brief.get("source_label"))
        if source_label:
            source_labels.append(source_label)
        if not updated_at:
            updated_at = _normalize_text(brief.get("updated_at"))

        for item in brief.get("items", []):
            title = _normalize_text(item.get("title"))
            summary = _normalize_text(item.get("summary"))
            key = f"{title}|{summary[:40]}"
            if not title or key in seen_titles:
                continue
            seen_titles.add(key)
            collected.append(item)
            if len(collected) >= 10:
                break
        if len(collected) >= 10:
            break

    if not collected:
        return None

    return {
        "status": "ok",
        "brief_date": today_text,
        "source": "merged",
        "source_label": " + ".join(_dedupe(source_labels[:3])),
        "updated_at": updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "items": collected,
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def get_market_news_brief(force_refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    today_text = datetime.now().strftime("%Y-%m-%d")
    if (
        not force_refresh
        and NEWS_CACHE["data"] is not None
        and NEWS_CACHE["brief_date"] == today_text
        and now < NEWS_CACHE["expires_at"]
    ):
        return NEWS_CACHE["data"]

    errors: list[str] = []
    eastmoney_brief: dict[str, Any] | None = None
    caixin_brief: dict[str, Any] | None = None
    cls_brief: dict[str, Any] | None = None

    try:
        eastmoney_brief = fetch_eastmoney_global_brief(today_text)
    except Exception as exc:  # pragma: no cover
        errors.append(f"stock_info_global_em: {exc}")

    try:
        caixin_brief = fetch_caixin_market_brief()
    except Exception as exc:  # pragma: no cover
        errors.append(f"stock_news_main_cx: {exc}")

    try:
        cls_brief = fetch_cls_focus_brief(today_text)
    except Exception as exc:  # pragma: no cover
        errors.append(f"stock_info_global_cls: {exc}")

    brief = _merge_news_briefs(
        [eastmoney_brief, caixin_brief, cls_brief],
        today_text=today_text,
    )

    if brief is None:
        brief = {
            "status": "error",
            "brief_date": today_text,
            "source": "unavailable",
            "source_label": "新闻接口暂不可用",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": [
                build_brief_item(
                    title="新闻简报暂不可用",
                    summary="AKShare 财经新闻源本轮未成功返回数据，页面保留筛选功能，稍后可再次刷新简报。",
                    published_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    source="fallback",
                )
            ],
        }

    brief["generated_at"] = datetime.now().isoformat(timespec="seconds")
    brief["errors"] = errors

    NEWS_CACHE.update(
        {
            "expires_at": now + NEWS_CACHE_TTL_SECONDS,
            "brief_date": today_text,
            "data": brief,
        }
    )
    return brief
