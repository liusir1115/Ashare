from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERDATA_DIR = PROJECT_ROOT / "result" / "userdata"
USERDATA_DIR.mkdir(parents=True, exist_ok=True)


def _safe_session(session: str | None) -> str:
    raw = str(session or "postclose").strip().lower()
    return "midday" if raw == "midday" else "postclose"


def _context_path(kind: str, session: str | None) -> Path:
    return USERDATA_DIR / f"postclose_{kind}_{_safe_session(session)}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_market_review_context(payload: dict[str, Any], session: str | None) -> None:
    _write_json(_context_path("market_review", session), payload)


def load_market_review_context(session: str | None) -> dict[str, Any] | None:
    return _read_json(_context_path("market_review", session))


def save_holdings_review_context(payload: dict[str, Any], session: str | None) -> None:
    _write_json(_context_path("holdings_review", session), payload)


def load_holdings_review_context(session: str | None) -> dict[str, Any] | None:
    return _read_json(_context_path("holdings_review", session))


def save_operations_review_context(payload: dict[str, Any], session: str | None) -> None:
    _write_json(_context_path("operations_review", session), payload)


def load_operations_review_context(session: str | None) -> dict[str, Any] | None:
    return _read_json(_context_path("operations_review", session))
