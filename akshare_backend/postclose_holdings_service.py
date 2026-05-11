from __future__ import annotations

import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .postclose_concept_service import build_holdings_concept_snapshot
    from .postclose_driver_service import build_stock_driver_analysis
    from .postclose_fact_builder import build_postclose_fact_summary
    from .postclose_holdings_llm_service import generate_holdings_review_with_llm
    from .postclose_market_service import build_postclose_market_review
    from .postclose_tushare_provider import fetch_postclose_facts
    from .premarket_tushare_screen_service import fetch_tushare_snapshot
    from .tushare_provider import (
        fetch_fund_basic_full,
        fetch_fund_daily_for_trade_date,
        get_recent_trade_date_text,
    )
except ImportError:
    from postclose_concept_service import build_holdings_concept_snapshot
    from postclose_driver_service import build_stock_driver_analysis
    from postclose_fact_builder import build_postclose_fact_summary
    from postclose_holdings_llm_service import generate_holdings_review_with_llm
    from postclose_market_service import build_postclose_market_review
    from postclose_tushare_provider import fetch_postclose_facts
    from premarket_tushare_screen_service import fetch_tushare_snapshot
    from tushare_provider import (
        fetch_fund_basic_full,
        fetch_fund_daily_for_trade_date,
        get_recent_trade_date_text,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERDATA_DIR = PROJECT_ROOT / "result" / "userdata"
HOLDINGS_DRAFT_PATH = USERDATA_DIR / "postclose_holdings_draft.json"
USERDATA_DIR.mkdir(parents=True, exist_ok=True)


class HoldingsValidationError(ValueError):
    """Raised when holdings payload is invalid."""


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if value is None:
        return None
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


def _normalize_symbol(raw_value: Any) -> str:
    text = str(raw_value or "").strip().upper()
    if not text:
        return ""
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) == 6:
        return digits
    return text


def _normalize_name_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_six_digit_code(value: str) -> bool:
    return len(value) == 6 and value.isdigit()


def _safe_float(raw_value: Any) -> float | None:
    text = str(raw_value or "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_pct(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "--"


def _format_amount_yi(value: Any) -> str:
    try:
        return f"{float(value) / 1e8:.2f} 亿元"
    except (TypeError, ValueError):
        return "--"


def _normalize_optional_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _detect_asset_type(symbol: str) -> str:
    if symbol.startswith(("5", "1")):
        return "etf"
    return "stock"


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


def _parse_hotspot_concepts(raw_value: Any) -> list[str]:
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
    return _dedupe_texts([part.strip().strip("\"'") for part in raw_text.split(",") if part.strip()])


def _build_hotspot_symbol_lookup(hotspot_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in hotspot_items:
        symbol = _normalize_symbol(item.get("ts_code"))
        if not symbol:
            continue
        concepts = _parse_hotspot_concepts(item.get("concept"))
        current = lookup.get(symbol, {})
        lookup[symbol] = {
            "name": str(item.get("ts_name") or item.get("name") or current.get("name") or "").strip(),
            "concepts": _dedupe_texts(list(current.get("concepts") or []) + concepts),
        }
    return lookup


def _save_holdings_draft(items: list[dict[str, Any]]) -> None:
    payload = {
        "updated_at": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
        "holdings": items,
    }
    HOLDINGS_DRAFT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_saved_holdings_draft() -> dict[str, Any]:
    if not HOLDINGS_DRAFT_PATH.exists():
        return {
            "status": "ok",
            "updated_at": None,
            "holdings": [],
        }
    try:
        payload = json.loads(HOLDINGS_DRAFT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "error",
            "updated_at": None,
            "holdings": [],
            "message": "Failed to read saved holdings draft.",
        }
    return {
        "status": "ok",
        "updated_at": payload.get("updated_at"),
        "holdings": payload.get("holdings") or [],
    }


def _validate_holdings_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    holdings = payload.get("holdings")
    if not isinstance(holdings, list) or not holdings:
        raise HoldingsValidationError("至少需要提交一条持仓记录。")

    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(holdings, start=1):
        if not isinstance(item, dict):
            raise HoldingsValidationError(f"第 {index} 条持仓不是合法对象。")

        query_text = str(item.get("symbol") or item.get("name") or "").strip()
        symbol = _normalize_symbol(query_text)
        direction = str(item.get("direction") or "").strip()
        cost = _safe_float(item.get("cost"))
        position_pct = _safe_float(item.get("position_pct"))
        reason = str(item.get("reason") or "").strip()

        if not symbol:
            raise HoldingsValidationError(f"第 {index} 条持仓缺少股票代码、ETF 代码或名称。")
        if not direction:
            raise HoldingsValidationError(f"第 {index} 条持仓缺少持仓方向。")
        if cost is None:
            raise HoldingsValidationError(f"第 {index} 条持仓缺少持仓成本。")
        if position_pct is None:
            raise HoldingsValidationError(f"第 {index} 条持仓缺少当前仓位。")

        normalized_items.append(
            {
                "symbol": symbol,
                "query_text": query_text,
                "direction": direction,
                "cost": cost,
                "position_pct": position_pct,
                "reason": reason,
                "asset_type": str(item.get("asset_type") or _detect_asset_type(symbol)).strip().lower(),
            }
        )

    return normalized_items


def _build_etf_snapshot(trade_date: str) -> pd.DataFrame:
    fund_basic_df = fetch_fund_basic_full()
    fund_daily_df = fetch_fund_daily_for_trade_date(trade_date)

    if fund_basic_df is None or fund_basic_df.empty or fund_daily_df is None or fund_daily_df.empty:
        return pd.DataFrame()

    working_basic = fund_basic_df.copy()
    working_daily = fund_daily_df.copy()

    working_basic["symbol"] = working_basic["ts_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    working_basic["market"] = "ETF"
    working_basic["industry"] = working_basic["fund_type"].fillna("ETF")

    working_daily["symbol"] = working_daily["ts_code"].astype(str).str.extract(r"(\d{6})", expand=False)
    working_daily["latest_price"] = pd.to_numeric(working_daily["close"], errors="coerce")
    working_daily["change_pct"] = pd.to_numeric(working_daily["pct_chg"], errors="coerce")
    working_daily["amount"] = pd.to_numeric(working_daily["amount"], errors="coerce") * 1000
    working_daily["turnover_rate"] = pd.NA

    merged = working_daily.merge(
        working_basic[["ts_code", "symbol", "name", "industry", "market"]],
        on=["ts_code", "symbol"],
        how="left",
    )
    merged["name_norm"] = merged["name"].astype(str).str.strip().str.upper()
    return merged[
        [
            "symbol",
            "ts_code",
            "name",
            "name_norm",
            "industry",
            "market",
            "latest_price",
            "change_pct",
            "amount",
            "turnover_rate",
        ]
    ].copy()


def _prepare_stock_snapshot(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    working_df = snapshot_df.copy()
    working_df["symbol"] = working_df["symbol"].astype(str).str.zfill(6)
    working_df["name_norm"] = working_df["name"].astype(str).str.strip().str.upper()
    return working_df


def _match_row_by_query(query: str, df: pd.DataFrame) -> pd.Series | None:
    if df.empty:
        return None

    if _is_six_digit_code(query):
        matched_df = df[df["symbol"] == query]
        if matched_df.empty:
            return None
        return matched_df.iloc[0]

    query_norm = _normalize_name_text(query)
    exact_df = df[df["name_norm"] == query_norm]
    if not exact_df.empty:
        return exact_df.iloc[0]

    startswith_df = df[df["name_norm"].str.startswith(query_norm, na=False)]
    if not startswith_df.empty:
        return startswith_df.iloc[0]

    contains_df = df[df["name_norm"].str.contains(query_norm, na=False)]
    if not contains_df.empty:
        return contains_df.iloc[0]

    return None


def _find_stock_fact(query: str, snapshot_df: pd.DataFrame) -> dict[str, Any] | None:
    row = _match_row_by_query(query, _prepare_stock_snapshot(snapshot_df))
    if row is None:
        return None
    return {
        "symbol": str(row.get("symbol") or query).strip(),
        "name": str(row.get("name") or query).strip(),
        "industry": str(row.get("industry") or "").strip() or "未匹配行业",
        "market": str(row.get("market") or "").strip() or "A股",
        "latest_price": row.get("latest_price"),
        "day_change_pct": row.get("change_pct"),
        "turnover_rate": row.get("turnover_rate"),
        "amount": row.get("amount"),
        "asset_type": "stock",
    }


def _find_etf_fact(query: str, etf_df: pd.DataFrame) -> dict[str, Any] | None:
    row = _match_row_by_query(query, etf_df)
    if row is None:
        return None
    return {
        "symbol": str(row.get("symbol") or query).strip(),
        "name": str(row.get("name") or query).strip(),
        "industry": str(row.get("industry") or "ETF").strip() or "ETF",
        "market": "ETF",
        "latest_price": row.get("latest_price"),
        "day_change_pct": row.get("change_pct"),
        "turnover_rate": row.get("turnover_rate"),
        "amount": row.get("amount"),
        "asset_type": "etf",
    }


def _build_driver_summary(concept_fact: dict[str, Any]) -> str:
    candidates = concept_fact.get("driver_candidates") or []
    if candidates:
        return " / ".join(candidates[:3])
    all_concepts = concept_fact.get("all_concepts") or []
    if all_concepts:
        return " / ".join(all_concepts[:3])
    return "待结合市场主线进一步确认"


def _build_holdings_facts(
    normalized_holdings: list[dict[str, Any]],
    snapshot_df: pd.DataFrame,
    etf_df: pd.DataFrame,
    fact_summary: dict[str, Any],
    hotspot_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summary_mainlines = {
        str(item).strip() for item in fact_summary.get("mainline_candidates", []) if str(item).strip()
    }
    summary_concepts = {
        str(item).strip() for item in fact_summary.get("concept_candidates", []) if str(item).strip()
    }
    hot_topics = [str(item).strip() for item in fact_summary.get("hot_topics", []) if str(item).strip()]
    hotspot_symbol_lookup = _build_hotspot_symbol_lookup(hotspot_items)

    concept_snapshot = build_holdings_concept_snapshot(
        holdings_codes=[item["symbol"] for item in normalized_holdings if item.get("asset_type") == "stock"],
        fact_summary=fact_summary,
        hotspot_items=hotspot_items,
    )

    results: list[dict[str, Any]] = []
    for item in normalized_holdings:
        symbol = item["symbol"]
        query_text = item.get("query_text") or symbol
        asset_type = item["asset_type"]

        fact = _find_etf_fact(query_text, etf_df) if asset_type == "etf" else _find_stock_fact(query_text, snapshot_df)
        if fact is None and asset_type == "stock":
            fact = _find_etf_fact(query_text, etf_df)
            asset_type = "etf" if fact else asset_type
        if fact is None and asset_type == "etf":
            fact = _find_stock_fact(query_text, snapshot_df)
            asset_type = "stock" if fact else asset_type

        if fact is None:
            raise HoldingsValidationError(f"未在当日市场快照中找到标的 {query_text}，请检查代码或名称是否正确。")

        latest_price = fact.get("latest_price")
        cost = float(item["cost"])
        position_pct = float(item["position_pct"])
        pnl_pct = ((float(latest_price) / cost - 1) * 100) if latest_price not in (None, 0) and cost else None

        industry = fact["industry"]
        concept_fact = dict(concept_snapshot.get(fact["symbol"], {}))
        if asset_type == "stock":
            driver_fact = build_stock_driver_analysis(
                symbol=fact["symbol"],
                name=fact["name"],
                concept_fact=concept_fact,
                fact_summary=fact_summary,
                hotspot_symbol_lookup=hotspot_symbol_lookup,
            )
            merged_candidates = _dedupe_texts(
                list(driver_fact.get("driver_candidates") or [])
                + list(concept_fact.get("driver_candidates") or [])
            )
            merged_evidence = _dedupe_texts(
                list(driver_fact.get("driver_evidence") or [])
                + list(concept_fact.get("driver_evidence") or [])
            )
            merged_all = _dedupe_texts(
                list(driver_fact.get("news_keywords") or [])
                + list(driver_fact.get("related_concepts") or [])
                + list(concept_fact.get("all_concepts") or [])
            )
            concept_fact.update(
                {
                    "driver_candidates": merged_candidates[:4],
                    "driver_evidence": merged_evidence,
                    "all_concepts": merged_all,
                    "keyword_concepts": driver_fact.get("keyword_concepts") or [],
                    "news_keywords": driver_fact.get("news_keywords") or [],
                }
            )
        market_overlap = concept_fact.get("market_overlap") or []
        hotspot_concepts = concept_fact.get("hotspot_concepts") or []
        board_memberships = concept_fact.get("board_memberships") or []
        driver_candidates = concept_fact.get("driver_candidates") or []
        driver_evidence = concept_fact.get("driver_evidence") or []

        is_mainline = bool(market_overlap) or industry in summary_mainlines
        is_secondary_candidate = any(concept in summary_concepts for concept in market_overlap) or bool(hotspot_concepts)

        results.append(
            {
                "symbol": fact["symbol"],
                "name": fact["name"],
                "direction": item["direction"],
                "asset_type": asset_type,
                "industry": industry,
                "market": fact["market"],
                "cost": round(cost, 3),
                "latest_price": round(float(latest_price), 3) if latest_price is not None else None,
                "position_pct": round(position_pct, 2),
                "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
                "day_change_pct": round(float(fact["day_change_pct"]), 2) if fact.get("day_change_pct") is not None else None,
                "turnover_rate": (
                    round(_normalize_optional_float(fact.get("turnover_rate")), 2)
                    if _normalize_optional_float(fact.get("turnover_rate")) is not None
                    else None
                ),
                "amount_text": _format_amount_yi(fact.get("amount")),
                "reason": item["reason"],
                "concepts": {
                    "all": concept_fact.get("all_concepts") or [],
                    "hotspot": hotspot_concepts,
                    "board_memberships": board_memberships,
                    "market_overlap": market_overlap,
                    "driver_candidates": driver_candidates,
                    "driver_evidence": driver_evidence,
                },
                "tags": {
                    "is_mainline_industry": is_mainline,
                    "is_secondary_candidate": is_secondary_candidate,
                    "hot_topics": hot_topics[:5],
                },
                "driver_summary": _build_driver_summary(concept_fact),
            }
        )

    return results


def _build_fallback_holdings_review(
    *,
    holdings_facts: list[dict[str, Any]],
    market_review: dict[str, Any],
) -> dict[str, Any]:
    report_detail = market_review.get("report_detail", {})
    headline = str(report_detail.get("close") or "").strip()
    focus = str(report_detail.get("focus") or "").strip()
    plan = str(report_detail.get("plan") or "").strip()

    aligned_count = 0
    risk_lines: list[str] = []
    next_lines: list[str] = []
    holding_reviews: list[dict[str, str]] = []

    for item in holdings_facts:
        driver_summary = item.get("driver_summary") or item["industry"]
        overlap = item.get("concepts", {}).get("market_overlap") or []
        all_concepts = item.get("concepts", {}).get("all") or []
        evidence = item.get("concepts", {}).get("driver_evidence") or []

        if item["asset_type"] == "etf":
            if item["tags"].get("is_mainline_industry"):
                verdict = "跟随主线"
                thesis = f"{item['name']} 更接近当前市场主线方向 {item['industry']}，适合作为风格跟随工具。"
                aligned_count += 1
            else:
                verdict = "中性观察"
                thesis = f"{item['name']} 属于 ETF 工具型持仓，仍需要确认其跟踪方向是否继续获得承接。"
        else:
            if overlap:
                verdict = "偏主线"
                thesis = (
                    f"{item['name']} 当前更值得从概念驱动而不是传统行业去看，"
                    f"它与当日市场共振的核心线索是 {' / '.join(overlap[:3])}。"
                )
                aligned_count += 1
            elif item["tags"].get("is_secondary_candidate"):
                verdict = "中性观察"
                thesis = (
                    f"{item['name']} 具备 {' / '.join(all_concepts[:3]) if all_concepts else item['industry']} 等概念线索，"
                    "但是否构成次日主攻方向，还需要看承接是否延续。"
                )
            else:
                verdict = "明显偏离"
                thesis = (
                    f"{item['name']} 暂未看到与当日主线强相关的概念共振，当前更像独立波动或边缘轮动。"
                )

        evidence_text = f" 证据：{evidence[0]}" if evidence else ""
        thesis = f"{thesis}{evidence_text}"

        pnl_text = _format_pct(item.get("pnl_pct"))
        if item.get("pnl_pct") is not None:
            risk = f"当前仓位 {item['position_pct']:.2f}%，浮盈浮亏 {pnl_text}，真实驱动先看 {driver_summary}。"
        else:
            risk = f"当前仓位 {item['position_pct']:.2f}%，需要先确认 {driver_summary} 是否还有次日承接。"

        if verdict == "明显偏离":
            next_step = "如果次日无法得到热点承接，应优先下调预期，避免用主观信念硬扛。"
            risk_lines.append(f"{item['name']} 偏离当前主线，若无承接应优先降低预期。")
        elif verdict == "中性观察":
            next_step = "优先观察是否出现放量承接或与主线共振，确认后再决定是否继续持有。"
        else:
            next_step = "次日重点盯住概念承接强度、量能延续和高位反馈，再决定持有或收缩。"

        next_lines.append(f"{item['name']}：先看 {driver_summary} 是否继续获得承接。")
        holding_reviews.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "verdict": verdict,
                "thesis": thesis,
                "risk": risk,
                "next_step": next_step,
            }
        )

    summary = (
        f"当前共复盘 {len(holdings_facts)} 条持仓，其中 {aligned_count} 条更贴近当前主线。"
        f"{' 市场总收口为：' + headline if headline else ''}"
    )
    return {
        "portfolio_summary": summary,
        "risk_flags": "；".join(risk_lines[:3]) if risk_lines else (focus or "当前持仓更需要继续确认是否获得次日承接。"),
        "action_plan": plan or "次日优先确认主线承接、仓位暴露和偏离主线个股的处理顺序。",
        "holdings": holding_reviews,
        "next_watch": next_lines[:6],
    }


def build_postclose_holdings_review(payload: dict[str, Any], force_refresh: bool = False) -> dict[str, Any]:
    normalized_holdings = _validate_holdings_payload(payload)
    _save_holdings_draft(
        [
            {
                "symbol": item["symbol"],
                "asset_type": item["asset_type"],
                "direction": item["direction"],
                "cost": item["cost"],
                "position_pct": item["position_pct"],
                "reason": item["reason"],
            }
            for item in normalized_holdings
        ]
    )

    market_review = build_postclose_market_review(force_refresh=force_refresh)
    snapshot_df, trade_date, _ = fetch_tushare_snapshot(force_refresh=force_refresh)
    postclose_facts = fetch_postclose_facts()
    fact_summary = build_postclose_fact_summary(postclose_facts)
    hotspot_items = postclose_facts.get("hotspots", {}).get("top_ranked", [])
    etf_df = _build_etf_snapshot(trade_date or get_recent_trade_date_text())
    holdings_facts = _build_holdings_facts(
        normalized_holdings,
        snapshot_df,
        etf_df,
        fact_summary,
        hotspot_items,
    )
    fallback_review = _build_fallback_holdings_review(
        holdings_facts=holdings_facts,
        market_review=market_review,
    )

    llm_status = {
        "enabled": False,
        "used": False,
        "provider": "deepseek",
        "model": None,
        "message": "LLM not configured. Using fallback holdings review.",
    }
    review_payload = fallback_review
    errors: list[str] = []

    try:
        llm_review = generate_holdings_review_with_llm(
            trade_date=trade_date,
            market_review=market_review,
            holdings_facts=holdings_facts,
            fallback_report=fallback_review,
        )
        review_payload = {
            **fallback_review,
            **llm_review,
        }
        llm_meta = llm_review.get("llm_meta") or {}
        llm_status = {
            "enabled": True,
            "used": True,
            "provider": llm_meta.get("provider", "deepseek"),
            "model": llm_meta.get("model"),
            "message": "LLM holdings review generated successfully.",
        }
    except Exception as exc:  # pragma: no cover
        errors.append(f"holdings_review_llm: {exc}")

    response = {
        "status": "ok",
        "trade_date": trade_date,
        "holdings_input_count": len(normalized_holdings),
        "market_context": {
            "headline": market_review.get("report_detail", {}).get("close", ""),
            "focus": market_review.get("report_detail", {}).get("focus", ""),
            "plan": market_review.get("report_detail", {}).get("plan", ""),
        },
        "holdings_facts": holdings_facts,
        "review": review_payload,
        "llm_status": llm_status,
        "errors": errors,
    }
    return _sanitize_payload(response)
