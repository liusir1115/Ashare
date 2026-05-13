from __future__ import annotations

import json

from flask import Blueprint, Response, request

try:
    from .postclose_operations_service import build_postclose_operations_review, load_saved_operations_draft
    from .postclose_holdings_service import (
        HoldingsValidationError,
        build_postclose_holdings_review,
        load_saved_holdings_draft,
    )
    from .postclose_market_adapter import build_market_review_with_session
    from .postclose_qa_service import build_postclose_qa
except ImportError:
    from postclose_operations_service import build_postclose_operations_review, load_saved_operations_draft
    from postclose_holdings_service import (
        HoldingsValidationError,
        build_postclose_holdings_review,
        load_saved_holdings_draft,
    )
    from postclose_market_adapter import build_market_review_with_session
    from postclose_qa_service import build_postclose_qa


postclose_bp = Blueprint("postclose", __name__)


@postclose_bp.get("/api/postclose/market-review")
def postclose_market_review():
    force_refresh = request.args.get("refresh") == "1"
    session = request.args.get("session")
    payload = build_market_review_with_session(force_refresh=force_refresh, session=session)
    status_code = 200 if payload.get("status") != "fail" else 503
    return Response(
        json.dumps(payload, ensure_ascii=False, allow_nan=False),
        status=status_code,
        mimetype="application/json",
    )


@postclose_bp.post("/api/postclose/holdings-review")
def postclose_holdings_review():
    force_refresh = request.args.get("refresh") == "1"
    session = request.args.get("session")
    payload = request.get_json(silent=True) or {}
    try:
        result = build_postclose_holdings_review(payload, force_refresh=force_refresh, session=session)
        return Response(
            json.dumps(result, ensure_ascii=False, allow_nan=False),
            status=200,
            mimetype="application/json",
        )
    except HoldingsValidationError as exc:
        return Response(
            json.dumps(
                {
                    "status": "error",
                    "message": "持仓录入校验失败。",
                    "detail": str(exc),
                },
                ensure_ascii=False,
                allow_nan=False,
            ),
            status=400,
            mimetype="application/json",
        )


@postclose_bp.get("/api/postclose/holdings-draft")
def postclose_holdings_draft():
    payload = load_saved_holdings_draft()
    return Response(
        json.dumps(payload, ensure_ascii=False, allow_nan=False),
        status=200 if payload.get("status") == "ok" else 500,
        mimetype="application/json",
    )


@postclose_bp.get("/api/postclose/operations-draft")
def postclose_operations_draft():
    payload = load_saved_operations_draft()
    return Response(
        json.dumps(payload, ensure_ascii=False, allow_nan=False),
        status=200 if payload.get("status") == "ok" else 500,
        mimetype="application/json",
    )


@postclose_bp.post("/api/postclose/operations-review")
def postclose_operations_review():
    force_refresh = request.args.get("refresh") == "1"
    session = request.args.get("session")
    payload = request.get_json(silent=True) or {}
    try:
        result = build_postclose_operations_review(payload, force_refresh=force_refresh, session=session)
        return Response(
            json.dumps(result, ensure_ascii=False, allow_nan=False),
            status=200,
            mimetype="application/json",
        )
    except HoldingsValidationError as exc:
        return Response(
            json.dumps(
                {
                    "status": "error",
                    "message": "操作录入校验失败。",
                    "detail": str(exc),
                },
                ensure_ascii=False,
                allow_nan=False,
            ),
            status=400,
            mimetype="application/json",
        )


@postclose_bp.post("/api/postclose/qa")
def postclose_qa():
    payload = request.get_json(silent=True) or {}
    try:
        result = build_postclose_qa(payload)
        return Response(
            json.dumps(result, ensure_ascii=False, allow_nan=False),
            status=200,
            mimetype="application/json",
        )
    except ValueError as exc:
        return Response(
            json.dumps(
                {
                    "status": "error",
                    "message": "盘后问答参数校验失败。",
                    "detail": str(exc),
                },
                ensure_ascii=False,
                allow_nan=False,
            ),
            status=400,
            mimetype="application/json",
        )
