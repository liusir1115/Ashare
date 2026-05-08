from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from .service import (
        PayloadValidationError,
        build_capability_report,
        get_market_news_brief,
        list_saved_results,
        probe_snapshot,
        run_screen,
    )
except ImportError:
    from service import (
        PayloadValidationError,
        build_capability_report,
        get_market_news_brief,
        list_saved_results,
        probe_snapshot,
        run_screen,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)


@app.get("/api/health")
def health() -> tuple[dict, int]:
    return {
        "status": "ok",
        "message": "AKShare backend is ready.",
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
                    "message": "AKShare 拉取失败或字段处理异常。",
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
