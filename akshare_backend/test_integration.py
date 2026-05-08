from __future__ import annotations

import json

from app import app


def main() -> None:
    with app.test_client() as client:
        health = client.get("/api/health")
        capability = client.get("/api/capability")
        screen = client.get("/api/screen/run?mode=pre")

        payload = {
            "health": health.get_json(),
            "capability_count": len(capability.get_json()["filters"]),
            "screen_status_code": screen.status_code,
            "screen_summary": {},
        }

        screen_json = screen.get_json() or {}
        payload["screen_summary"] = {
            "mode": screen_json.get("mode"),
            "first_round_count": screen_json.get("first_round_count"),
            "final_result_count": screen_json.get("final_result_count"),
            "first_result": (screen_json.get("results") or [None])[0],
            "error": screen_json.get("detail"),
        }

        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
