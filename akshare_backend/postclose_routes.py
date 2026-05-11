from __future__ import annotations

import json

from flask import Blueprint, Response, request

try:
    from .postclose_holdings_service import (
        HoldingsValidationError,
        build_postclose_holdings_review,
        load_saved_holdings_draft,
    )
    from .postclose_market_service import build_postclose_market_review
except ImportError:
    from postclose_holdings_service import (
        HoldingsValidationError,
        build_postclose_holdings_review,
        load_saved_holdings_draft,
    )
    from postclose_market_service import build_postclose_market_review


postclose_bp = Blueprint("postclose", __name__)


@postclose_bp.get("/api/postclose/market-review")
def postclose_market_review():
    force_refresh = request.args.get("refresh") == "1"
    payload = build_postclose_market_review(force_refresh=force_refresh)
    status_code = 200 if payload.get("status") != "fail" else 503
    return Response(
        json.dumps(payload, ensure_ascii=False, allow_nan=False),
        status=status_code,
        mimetype="application/json",
    )


@postclose_bp.post("/api/postclose/holdings-review")
def postclose_holdings_review():
    force_refresh = request.args.get("refresh") == "1"
    payload = request.get_json(silent=True) or {}
    try:
        result = build_postclose_holdings_review(payload, force_refresh=force_refresh)
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
