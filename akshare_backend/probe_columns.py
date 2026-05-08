from __future__ import annotations

import json

from service import build_capability_report, probe_snapshot, run_screen


def main() -> None:
    snapshot = probe_snapshot()
    capability = build_capability_report()
    result = run_screen()

    print("=== AKShare 快照列名 ===")
    print(json.dumps(snapshot, ensure_ascii=False, default=str, indent=2))
    print()
    print("=== 前端筛选项支持情况 ===")
    print(json.dumps(capability, ensure_ascii=False, default=str, indent=2))
    print()
    print("=== 默认筛选结果（前 10） ===")
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
