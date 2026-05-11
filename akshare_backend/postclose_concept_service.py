from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .tushare_provider import fetch_stock_basic_full, get_tushare_client
except ImportError:
    from tushare_provider import fetch_stock_basic_full, get_tushare_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "result" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

VALID_THEME_TYPES = {"N", "I", "S"}
GENERIC_CONCEPT_KEYWORDS = [
    "同花顺全A",
    "沪深",
    "中证",
    "深市",
    "主板",
    "成份股",
    "成分股",
    "融资融券",
    "陆股通",
    "深股通",
    "破净股",
    "低估值",
    "减持新规",
    "行业龙头",
    "激进投资",
    "中盘",
    "大盘",
    "小盘",
    "高股息",
    "高分红",
    "不可减持",
    "同花顺热股",
    "同花顺情绪指数",
    "龙虎榜指数",
    "高贝塔值",
    "百日新高",
    "近期新高",
    "近期强势",
    "最近多板",
    "昨日涨停表现",
    "昨日首板表现",
    "昨日连板",
    "昨日炸板股",
    "昨日打板表现",
    "昨日打首板表现",
    "昨日打首板以上表现",
    "昨日高振幅",
    "昨日非ST炸板",
    "昨日非ST打板",
    "昨日非ST首板",
    "昨日非ST连板",
    "昨日非ST二板表现",
    "昨日非ST涨停表现",
    "创历史新高",
    "减持计划",
]


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    digits = "".join(char for char in text if char.isdigit())
    return digits[-6:] if len(digits) >= 6 else text


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


def _is_generic_concept(name: str) -> bool:
    text = str(name or "").strip()
    if not text:
        return True
    if any(keyword in text for keyword in GENERIC_CONCEPT_KEYWORDS):
        return True
    if text.endswith("(A股)"):
        return True
    if text.startswith("昨日") or text.startswith("近期") or text.startswith("最近"):
        return True
    return False


def _parse_concept_list(raw_value: Any) -> list[str]:
    if raw_value in (None, ""):
        return []
    if isinstance(raw_value, list):
        return _dedupe_texts([str(item).strip() for item in raw_value])

    raw_text = str(raw_value).strip()
    if not raw_text:
        return []
    if raw_text.startswith("[") and raw_text.endswith("]"):
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                return _dedupe_texts([str(item).strip() for item in parsed])
        except json.JSONDecodeError:
            pass
    for separator in ["、", ",", "，", "/", "|"]:
        if separator in raw_text:
            return _dedupe_texts([item.strip() for item in raw_text.split(separator)])
    return [raw_text]


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


def _fetch_ths_index_frame() -> pd.DataFrame:
    cache_path = CACHE_DIR / "ths_index_a.json"
    cached = _load_cache(cache_path)
    if cached and isinstance(cached.get("rows"), list):
        return pd.DataFrame(cached["rows"])

    pro = get_tushare_client()
    df = pro.ths_index(exchange="A")
    if df is None or df.empty:
        return pd.DataFrame()
    _save_cache(cache_path, {"rows": df.to_dict(orient="records")})
    return df.copy()


def _fetch_board_meta(board_code: str) -> dict[str, Any]:
    normalized_board_code = str(board_code or "").strip().upper()
    cache_path = CACHE_DIR / f"ths_index_meta_{normalized_board_code.replace('.', '_')}.json"
    cached = _load_cache(cache_path)
    if cached:
      return cached

    pro = get_tushare_client()
    try:
        df = pro.ths_index(ts_code=normalized_board_code)
    except Exception:
        payload = {"ts_code": normalized_board_code, "name": "", "type": ""}
        _save_cache(cache_path, payload)
        return payload

    if df is None or df.empty:
        payload = {"ts_code": normalized_board_code, "name": "", "type": ""}
    else:
        row = df.iloc[0]
        payload = {
            "ts_code": normalized_board_code,
            "name": str(row.get("name") or "").strip(),
            "type": str(row.get("type") or "").strip(),
        }
    _save_cache(cache_path, payload)
    return payload


def _fetch_memberships_by_stock(symbol: str) -> list[dict[str, str]]:
    normalized_symbol = _normalize_symbol(symbol)
    if not normalized_symbol:
        return []

    cache_path = CACHE_DIR / f"ths_membership_by_stock_{normalized_symbol}.json"
    cached = _load_cache(cache_path)
    if cached and isinstance(cached.get("boards"), list):
        return cached["boards"]

    exchange = "SZ" if normalized_symbol.startswith(("0", "1", "2", "3")) else "SH"
    con_code = f"{normalized_symbol}.{exchange}"
    pro = get_tushare_client()
    df = pro.ths_member(con_code=con_code)
    if df is None or df.empty:
        return []

    board_codes = _dedupe_texts(df["ts_code"].astype(str).tolist())
    boards: list[dict[str, str]] = []
    for board_code in board_codes:
        meta = _fetch_board_meta(board_code)
        board_type = str(meta.get("type") or "").strip()
        board_name = str(meta.get("name") or "").strip()
        if board_type not in VALID_THEME_TYPES or not board_name or _is_generic_concept(board_name):
            continue
        boards.append(
            {
                "ts_code": board_code,
                "name": board_name,
                "type": board_type,
            }
        )
    payload = {"boards": boards}
    _save_cache(cache_path, payload)
    return boards


def _build_hotspot_lookup(hotspot_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in hotspot_items:
        symbol = _normalize_symbol(item.get("ts_code"))
        if not symbol:
            continue
        concepts = _parse_concept_list(item.get("concept"))
        current = lookup.get(symbol, {})
        rank_value = item.get("rank")
        hot_value = item.get("hot")
        reason = str(item.get("rank_reason") or "").strip()
        merged_concepts = _dedupe_texts(current.get("concepts", []) + concepts)
        lookup[symbol] = {
            "concepts": merged_concepts,
            "rank": rank_value if current.get("rank") is None else min(current.get("rank"), rank_value),
            "hot": hot_value if current.get("hot") is None else max(current.get("hot"), hot_value),
            "rank_reason": reason or current.get("rank_reason") or "",
        }
    return lookup


def _build_stock_name_lookup() -> dict[str, str]:
    try:
        basic_df = fetch_stock_basic_full()
    except Exception:
        return {}
    if basic_df is None or basic_df.empty:
        return {}
    return {
        _normalize_symbol(row.get("ts_code") or row.get("symbol")): str(row.get("name") or "").strip()
        for _, row in basic_df.iterrows()
    }


def build_holdings_concept_snapshot(
    *,
    holdings_codes: list[str],
    fact_summary: dict[str, Any],
    hotspot_items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    normalized_codes = [_normalize_symbol(code) for code in holdings_codes if _normalize_symbol(code)]
    hotspot_lookup = _build_hotspot_lookup(hotspot_items)
    market_topics = _dedupe_texts(
        [str(item).strip() for item in fact_summary.get("concept_candidates", [])]
        + [str(item).strip() for item in fact_summary.get("hot_topics", [])]
    )
    stock_name_lookup = _build_stock_name_lookup()

    snapshot: dict[str, dict[str, Any]] = {}
    for code in normalized_codes:
        hotspot_info = hotspot_lookup.get(code, {})
        hotspot_concepts = _dedupe_texts(hotspot_info.get("concepts", []))
        membership_rows = _fetch_memberships_by_stock(code)
        member_concepts = _dedupe_texts(
            [row.get("name", "") for row in membership_rows if not _is_generic_concept(row.get("name", ""))]
        )
        all_concepts = _dedupe_texts(
            [concept for concept in hotspot_concepts + member_concepts if not _is_generic_concept(concept)]
        )
        market_overlap = _dedupe_texts(
            [
                concept
                for concept in all_concepts
                for market_topic in market_topics
                if _concept_match(concept, market_topic)
            ]
        )

        primary_candidates = market_overlap or hotspot_concepts or member_concepts
        evidence_lines: list[str] = []
        if hotspot_concepts:
            evidence_lines.append(f"热股概念映射：{' / '.join(hotspot_concepts[:4])}")
        if market_overlap:
            evidence_lines.append(f"与当日市场共振：{' / '.join(market_overlap[:4])}")
        if member_concepts:
            evidence_lines.append(f"同花顺概念归属：{' / '.join(member_concepts[:6])}")
        rank_reason = str(hotspot_info.get("rank_reason") or "").strip()
        if rank_reason:
            evidence_lines.append(f"热股理由：{rank_reason[:140]}")
        if hotspot_info.get("rank") not in (None, ""):
            evidence_lines.append(f"热股榜位：第 {hotspot_info.get('rank')} 名")

        snapshot[code] = {
            "symbol": code,
            "name": stock_name_lookup.get(code, ""),
            "all_concepts": all_concepts,
            "hotspot_concepts": hotspot_concepts,
            "board_memberships": member_concepts,
            "market_overlap": market_overlap,
            "driver_candidates": primary_candidates[:4],
            "driver_evidence": evidence_lines,
            "hot_rank": hotspot_info.get("rank"),
            "hot_value": hotspot_info.get("hot"),
        }

    return snapshot
