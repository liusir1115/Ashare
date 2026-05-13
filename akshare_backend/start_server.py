from __future__ import annotations

import os

try:
    from .app import app
except ImportError:
    from app import app


def _get_host() -> str:
    return os.getenv("ASHARE_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _get_port() -> int:
    raw = os.getenv("ASHARE_PORT", "5000").strip() or "5000"
    try:
        return int(raw)
    except ValueError:
        return 5000


def _get_debug() -> bool:
    raw = os.getenv("ASHARE_DEBUG", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    app.run(host=_get_host(), port=_get_port(), debug=_get_debug())
