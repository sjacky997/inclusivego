"""從求解器的單格敏感度分析，抽出「脆弱格」清單（供示意地圖標記用）。

脆弱格定義：該站該維度上下各偏一級，會改變它在至少一個情境下的納入狀態。
此清單不手寫，一律由 sim_sensory.oat 重算，避免地圖標記與穩健度報告漂移。

執行：python3 scripts/fragile_cells.py            # 重新生成 data/fragile-cells.json
     python3 scripts/fragile_cells.py --check    # 只比對，不一致則 exit 1（CI 用）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver.planner import load_facilities  # noqa: E402
from scripts.sim_sensory import DIMS, SCENARIOS, Scenario, oat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fragile-cells.json"


def build() -> dict:
    payload = load_facilities()
    scenarios = [Scenario(label, budget, handling) for label, budget, handling in SCENARIOS]
    rows = oat(payload, scenarios)

    cells: dict[tuple[str, str], dict] = {}
    for r in rows:
        if not (r["flip_plus1"] or r["flip_minus1"]):
            continue
        key = (r["station_id"], r["dim"])
        c = cells.setdefault(
            key,
            {
                "id": r["station_id"],
                "station": r["station"],
                "dim": r["dim"],
                "value": r["value"],
                "scenarios": [],
            },
        )
        c["scenarios"].append(r["scenario"])
        # 方向：值 5 只要「降一級」就會被納入；值 3 只要「升一級」就會被排除
        c["relax_flips"] = c.get("relax_flips", False) or bool(
            r["value"] == 5 and r["flip_minus1"]
        )
        c["tighten_flips"] = c.get("tighten_flips", False) or bool(
            r["value"] == 3 and r["flip_plus1"]
        )

    ordered = sorted(cells.values(), key=lambda c: (c["id"], c["dim"]))
    return {
        "note": "由 scripts/fragile_cells.py 重算生成，勿手改；來源為 sim_sensory.oat 的單格擾動。",
        "cells_total": len(payload["facilities"]) * len(DIMS),
        "fragile_cells": len(ordered),
        "fragile_stations": len({c["id"] for c in ordered}),
        "cells": ordered,
    }


def main() -> int:
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        if not OUT.exists():
            print(f"MISSING {OUT}")
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print("fragile-cells.json 與重算結果不一致，請執行 python3 scripts/fragile_cells.py")
            return 1
        print(f"fragile cells OK：{data['fragile_cells']} 格 / {data['fragile_stations']} 站")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(
        f"已寫入 {OUT.relative_to(ROOT)}：{data['fragile_cells']} 格 / "
        f"{data['fragile_stations']} 站"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
