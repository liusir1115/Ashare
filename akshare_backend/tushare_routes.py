from __future__ import annotations

from flask import Blueprint, request

try:
    from .tushare_service import build_probe_response, build_sample_screen_response
except ImportError:
    from tushare_service import build_probe_response, build_sample_screen_response


tushare_bp = Blueprint("tushare", __name__, url_prefix="/api/tushare")


@tushare_bp.get("/probe")
def tushare_probe():
    trade_date = request.args.get("trade_date")
    return build_probe_response(trade_date=trade_date), 200


@tushare_bp.get("/sample-screen")
def tushare_sample_screen():
    trade_date = request.args.get("trade_date")
    return build_sample_screen_response(trade_date=trade_date), 200
