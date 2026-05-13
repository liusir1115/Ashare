from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from .backtest_compare_service import compare_backtest_strategies
    from .backtest_service import list_saved_backtests, run_backtest
    from .premarket_strategy_llm_service import parse_strategy_to_payload
    from .postclose_routes import postclose_bp
    from .service import (
        PayloadValidationError,
        build_capability_report,
        get_market_news_brief,
        list_saved_results,
        probe_snapshot,
        run_screen,
    )
    from .tushare_routes import tushare_bp
except ImportError:
    from backtest_compare_service import compare_backtest_strategies
    from backtest_service import list_saved_backtests, run_backtest
    from premarket_strategy_llm_service import parse_strategy_to_payload
    from postclose_routes import postclose_bp
    from service import (
        PayloadValidationError,
        build_capability_report,
        get_market_news_brief,
        list_saved_results,
        probe_snapshot,
        run_screen,
    )
    from tushare_routes import tushare_bp


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)
app.register_blueprint(postclose_bp)
app.register_blueprint(tushare_bp)


@app.get("/api/health")
def health() -> tuple[dict, int]:
    return {
        "status": "ok",
        "message": "Ashare backend is ready.",
    }, 200


@app.get("/api/capability")
def capability() -> tuple[dict, int]:
    return build_capability_report(), 200


@app.get("/api/probe")
def probe() -> tuple[dict, int]:
    return probe_snapshot(), 200


@app.get("/api/history")
def history() -> tuple[dict, int]:
    return {
        "status": "ok",
        "items": list_saved_results(),
    }, 200


@app.get("/api/news/brief")
def news_brief() -> tuple[dict, int]:
    force_refresh = request.args.get("refresh") == "1"
    return get_market_news_brief(force_refresh=force_refresh), 200


@app.get("/api/backtest/history")
def backtest_history() -> tuple[dict, int]:
    return {
        "status": "ok",
        "items": list_saved_backtests(),
    }, 200


@app.route("/api/screen/run", methods=["GET", "POST"])
def screen_run() -> tuple[dict, int]:
    payload = request.get_json(silent=True) or {}
    mode = request.args.get("mode")
    if mode:
        payload["mode"] = mode

    try:
        return jsonify(run_screen(payload)), 200
    except PayloadValidationError as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "筛选参数校验失败。",
                    "detail": str(exc),
                }
            ),
            400,
        )
    except Exception as exc:  # pragma: no cover
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Tushare 数据拉取失败或字段处理异常。",
                    "detail": str(exc),
                }
            ),
            503,
        )


@app.post("/api/backtest/run")
def backtest_run() -> tuple[dict, int]:
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(run_backtest(payload)), 200
    except PayloadValidationError as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "回测参数校验失败。",
                    "detail": str(exc),
                }
            ),
            400,
        )
    except Exception as exc:  # pragma: no cover
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "回测执行失败。",
                    "detail": str(exc),
                }
            ),
            503,
        )


@app.post("/api/backtest/compare")
def backtest_compare() -> tuple[dict, int]:
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "").strip()
    current_payload = payload.get("current_payload") or {}
    history_years = int(payload.get("history_years", 3))
    holding_days = int(payload.get("holding_days", 3))
    top_n = int(payload.get("top_n", 10))
    execution_mode = str(payload.get("execution_mode", "fast")).strip().lower() or "fast"

    if not query:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "策略描述不能为空。",
                }
            ),
            400,
        )

    try:
        return (
            jsonify(
                compare_backtest_strategies(
                    query=query,
                    current_payload=current_payload,
                    history_years=history_years,
                    holding_days=holding_days,
                    top_n=top_n,
                    execution_mode=execution_mode,
                )
            ),
            200,
        )
    except PayloadValidationError as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "策略对比参数校验失败。",
                    "detail": str(exc),
                }
            ),
            400,
        )
    except Exception as exc:  # pragma: no cover
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "策略对比执行失败。",
                    "detail": str(exc),
                }
            ),
            503,
        )


@app.post("/api/strategy/parse")
def strategy_parse() -> tuple[dict, int]:
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "").strip()
    current_payload = payload.get("current_payload") or {}
    detected_strategy_tags = payload.get("detected_strategy_tags") or []

    if not query:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "策略描述不能为空。",
                }
            ),
            400,
        )

    try:
        return jsonify(parse_strategy_to_payload(query, current_payload=current_payload, detected_strategy_tags=detected_strategy_tags)), 200
    except PayloadValidationError as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "策略解析后的筛选条件校验失败。",
                    "detail": str(exc),
                }
            ),
            400,
        )
    except Exception as exc:  # pragma: no cover
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "策略解析失败。",
                    "detail": str(exc),
                }
            ),
            503,
        )


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_proxy(path: str):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
