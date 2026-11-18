"""比對穩健度模擬的關鍵數字與 scripts/expected_sim.json。

用途：讓「文件上寫的 16.7% → 89.7%」與「程式實際跑出的數字」無法分開。
任何人改了門檻、資料或擾動模型，這一步會紅，而不是靜靜地換掉結論。

用法：
    python3 scripts/sim_check.py
    python3 scripts/sim_check.py --update     # 確認變更合理後重寫基準
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sim_sensory  # noqa: E402

EXPECTED = ROOT / "scripts" / "expected_sim.json"
RATE_TOL = 0.002  # 比率允許的浮點誤差；超出即視為結論改變


def compare(expected: dict, actual: dict) -> list[str]:
    diffs: list[str] = []
    for key in ("seed", "runs", "cells_total", "stations_total", "fragile_cells",
                "fragile_stations", "combos_total", "combos_flip_1", "combos_flip_2"):
        if expected.get(key) != actual.get(key):
            diffs.append(f"{key}: 預期 {expected.get(key)}，實得 {actual.get(key)}")

    exp_sc = expected.get("scenarios", [])
    act_sc = actual.get("scenarios", [])
    if [s["label"] for s in exp_sc] != [s["label"] for s in act_sc]:
        diffs.append(f"情境清單不同：預期 {[s['label'] for s in exp_sc]}，實得 {[s['label'] for s in act_sc]}")
        return diffs

    for e, a in zip(exp_sc, act_sc):
        for key in ("baseline_size", "fixed_cells"):
            if e[key] != a[key]:
                diffs.append(f"[{e['label']}] {key}: 預期 {e[key]}，實得 {a[key]}")
        for key in ("mean_size", "identical", "jaccard", "jaccard_p05",
                    "identical_fixed", "jaccard_fixed"):
            if abs(float(e[key]) - float(a[key])) > RATE_TOL:
                diffs.append(f"[{e['label']}] {key}: 預期 {e[key]}，實得 {a[key]}")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description="比對穩健度模擬的基準數字")
    ap.add_argument("--update", action="store_true", help="把目前的結果寫回 expected_sim.json")
    args = ap.parse_args()

    if not EXPECTED.exists() and not args.update:
        print(f"找不到基準檔：{EXPECTED}")
        print("首次建立請跑 python3 scripts/sim_check.py --update")
        return 2

    payload = sim_sensory.load_facilities(ROOT / "data" / "facilities.json")
    expected = json.loads(EXPECTED.read_text(encoding="utf-8")) if EXPECTED.exists() else {}
    scenarios = [sim_sensory.Scenario(label, budget, handling)
                 for label, budget, handling in sim_sensory.SCENARIOS]

    print(f"重跑模擬（seed={expected.get('seed', 20261118)}，"
          f"runs={expected.get('runs', 1000)}）…")
    actual = sim_sensory.metrics(
        payload, scenarios,
        runs=int(expected.get("runs", 1000)),
        seed=int(expected.get("seed", 20261118)),
    )

    if args.update:
        EXPECTED.write_text(json.dumps(actual, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"已寫入基準：{EXPECTED.relative_to(ROOT)}")
        print("請一併更新 docs/sensory-robustness.md 的數字，兩處不一致就失去意義。")
        return 0

    diffs = compare(expected, actual)
    if diffs:
        print(f"\n穩健度數字與基準不符（{len(diffs)} 項）：")
        for d in diffs:
            print(f"  - {d}")
        print("\n若變更是有意的（改了門檻、資料或擾動模型），確認後跑：")
        print("  python3 scripts/sim_check.py --update")
        print("並同步改 docs/sensory-robustness.md 的數字。")
        return 1

    print(
        f"\n穩健度基準一致：{actual['fragile_cells']} / {actual['cells_total']} 格脆弱、"
        f"涉及 {actual['fragile_stations']} / {actual['stations_total']} 站；"
        f"半日完全一致 {actual['scenarios'][1]['identical']:.1%} → "
        f"複核後 {actual['scenarios'][1]['identical_fixed']:.1%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
