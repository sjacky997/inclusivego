"""感官值穩健度模擬（蒙特卡羅＋單格擾動）。

用途：不改變任何求解器邏輯，只回答一個問題——「如果現有的感官估值各錯一級，
路線會不會變、哪幾格最關鍵」。輸出可用來決定現場複核的優先次序。

用法：
    python3 scripts/sim_sensory.py
    python3 scripts/sim_sensory.py --runs 2000 --seed 42
    python3 scripts/sim_sensory.py --csv sim.csv --markdown docs/sensory-robustness.md

說明：
- 擾動模型：每格維持原值的機率 0.6，+1 與 -1 各 0.2，結果夾在 1–5。
  這是「誤差一級」假設，不代表真實分佈；換分佈只要改 SHIFT_WEIGHTS。
- 聯合抽樣（joint）：一次擾動全部 136 格，用來看在整體不確定下的路線穩定度。
- 單格擾動（oat）：每次只動一格，用來看哪一格的錯會直接改變決策。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver.planner import Preferences, load_facilities, plan  # noqa: E402

DIMS = ["sound", "light", "crowd", "enclosed", "smell", "cold", "wet", "motion"]
SHIFT_WEIGHTS = {-1: 0.2, 0: 0.6, 1: 0.2}

SCENARIOS = [
    ("2h/避免高", 120, "avoid-high"),
    ("半日/避免高", 240, "avoid-high"),
    ("全日/避免高", 420, "avoid-high"),
    ("半日/避免中以上", 240, "avoid-medium"),
]


@dataclass(frozen=True)
class Scenario:
    label: str
    budget: int
    handling: str

    def prefs(self) -> Preferences:
        return Preferences(
            budget_min=self.budget,
            triggers=["sound", "crowd"],
            handling=self.handling,
            rest_interval=45,
            zone_walk=8,
        )


def snapshot(payload: dict) -> dict:
    return json.loads(json.dumps(payload))


def route_ids(plan_result) -> list[str]:
    return [s.id for s in plan_result.stops]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def shift(payload: dict, station_id: str, dim: str, delta: int) -> dict:
    """回傳擾動後的 payload（深拷貝），值夾在 1–5。"""
    out = snapshot(payload)
    for f in out["facilities"]:
        if f["id"] == station_id:
            v = f["sensory"][dim] + delta
            f["sensory"][dim] = max(1, min(5, v))
            break
    return out


def joint_runs(payload: dict, scenario: Scenario, runs: int, rng: random.Random,
               fixed: set | None = None) -> dict:
    base = route_ids(plan(payload, scenario.prefs()))
    base_set = set(base)
    all_ids = [f["id"] for f in payload["facilities"]]
    included = {sid: 0 for sid in all_ids}
    sizes: list[int] = []
    sims: list[float] = []
    identical = 0
    for _ in range(runs):
        p = snapshot(payload)
        for f in p["facilities"]:
            for dim in DIMS:
                if fixed and (f["id"], dim) in fixed:
                    continue
                d = rng.choices(list(SHIFT_WEIGHTS), weights=list(SHIFT_WEIGHTS.values()))[0]
                f["sensory"][dim] = max(1, min(5, f["sensory"][dim] + d))
        res = plan(p, scenario.prefs())
        ids = route_ids(res)
        for sid in ids:
            included[sid] += 1
        sizes.append(len(ids))
        sims.append(jaccard(base, ids))
        if set(ids) == base_set:
            identical += 1
    sims.sort()
    return {
        "label": scenario.label,
        "baseline_size": len(base),
        "baseline_route": base,
        "mean_size": sum(sizes) / runs,
        "jaccard_mean": sum(sims) / runs,
        "jaccard_p05": sims[int(0.05 * runs)],
        "identical_rate": identical / runs,
        "inclusion": {sid: c / runs for sid, c in included.items()},
    }


def oat(payload: dict, scenarios: list[Scenario]) -> list[dict]:
    """單格擾動：每格分別 -1 / +1 / -2 / +2，記錄是否改變該站在各情境下的納入狀態。"""
    rows = []
    for f in payload["facilities"]:
        sid, name = f["id"], f["name"]
        for dim in DIMS:
            value = f["sensory"][dim]
            for scenario in scenarios:
                base = set(route_ids(plan(payload, scenario.prefs())))
                flips = {}
                for delta in (1, -1, 2, -2):
                    p = shift(payload, sid, dim, delta)
                    now = set(route_ids(plan(p, scenario.prefs())))
                    flips[delta] = sid not in base and sid in now or sid in base and sid not in now
                rows.append(
                    {
                        "station_id": sid,
                        "station": name,
                        "dim": dim,
                        "value": value,
                        "scenario": scenario.label,
                        "flip_plus1": flips[1],
                        "flip_minus1": flips[-1],
                        "flip_plus2": flips[2],
                        "flip_minus2": flips[-2],
                        "in_baseline": sid in base,
                    }
                )
    return rows


def summarize(payload: dict, joints: list[dict], rows: list[dict]) -> str:
    lines = []
    lines.append("## 一、整體路線穩定度（聯合擾動）\n")
    lines.append("| 情境 | 基線站數 | 平均站數 | 路線相似度（Jaccard 均值） | 最差 5% 相似度 | 完全一致比例 |")
    lines.append("|---|---|---|---|---|---|")
    for j in joints:
        lines.append(
            f"| {j['label']} | {j['baseline_size']} | {j['mean_size']:.1f} | "
            f"{j['jaccard_mean']:.2f} | {j['jaccard_p05']:.2f} | {j['identical_rate']:.1%} |"
        )

    lines.append("\n## 二、每站納入機率（半日/避免高）\n")
    half = next(j for j in joints if j["label"] == "半日/避免高")
    lines.append("| 站 | 基線 | 納入機率 | 變化 |")
    lines.append("|---|---|---|---|")
    for f in payload["facilities"]:
        sid = f["id"]
        prob = half["inclusion"][sid]
        base = "納入" if sid in half["baseline_route"] else "排除"
        lines.append(f"| {f['name']} | {base} | {prob:.0%} | {abs(prob - (1.0 if sid in half['baseline_route'] else 0.0)):.0%} |")

    flips1 = [r for r in rows if r["flip_plus1"] or r["flip_minus1"]]
    flips2only = [
        r for r in rows
        if (r["flip_plus2"] or r["flip_minus2"]) and not (r["flip_plus1"] or r["flip_minus1"])
    ]
    cells = {(r["station_id"], r["dim"]) for r in flips1}
    lines.append("\n## 三、單格擾動（只改一格一級）\n")
    lines.append(
        f"- {len(rows)} 個「格 × 情境」組合中，**{len(flips1)} 個**在一級擾動下就改變了該站的去留，"
        f"另有 {len(flips2only)} 個要錯兩級才會翻轉。"
    )
    lines.append(
        f"- 換算到格：**{len(cells)} / 136 格**在一級內脆弱，涉及 {len({r['station_id'] for r in flips1})} 站。"
    )
    both1 = [r for r in flips1 if r["flip_plus1"] and r["flip_minus1"]]
    lines.append(
        f"- 同一格上下各錯一級都會翻轉的有 {len({(r['station_id'], r['dim']) for r in both1})} 格："
        "這類格無論往哪邊偏都無法自證，現場必須直接量。"
    )
    lines.append(
        "- 擾動方向不對稱：低估感官值只會讓更多站進路線（平均站數高於基線），"
        "高估則只會讓已排除的站永遠進不來。誤差不是隨機噪音，而是有方向的偏見。"
    )
    lines.append("\n最敏感的前 12 格：\n")
    lines.append("| 站 | 維度 | 現值 | 情境 | +1 翻轉 | -1 翻轉 |")
    lines.append("|---|---|---|---|---|---|")
    seen = set()
    picked = 0
    for r in sorted(flips1, key=lambda x: (x["dim"] not in ("sound", "crowd"), x["station"])):
        key = (r["station_id"], r["dim"])
        if key in seen:
            continue
        seen.add(key)
        picked += 1
        lines.append(
            f"| {r['station']} | {r['dim']} | {r['value']} | {r['scenario']} | "
            f"{'是' if r['flip_plus1'] else '—'} | {'是' if r['flip_minus1'] else '—'} |"
        )
        if picked >= 12:
            break
    lines.append(
        "\n> 擾動分佈為維持 0.6、±1 各 0.2，值夾在 1–5；這是「誤差一級」的假設，"
        "不代表真值分佈。所有數字都是「若假設成立會怎樣」，不是「實際會怎樣」。"
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="感官值穩健度模擬")
    ap.add_argument("--runs", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--data", default=str(ROOT / "data" / "facilities.json"))
    ap.add_argument("--csv", default="")
    ap.add_argument("--markdown", default="")
    ap.add_argument(
        "--fix-fragile",
        action="store_true",
        help="把各情境下一級內脆弱（m=1）的格視為已實測，重跑聯合抽樣，量化複核的收益",
    )
    args = ap.parse_args()

    payload = load_facilities(Path(args.data))
    scenarios = [Scenario(label, budget, handling) for label, budget, handling in SCENARIOS]
    rng = random.Random(args.seed)

    joints = [joint_runs(payload, s, args.runs, rng) for s in scenarios]
    rows = oat(payload, scenarios)

    for j in joints:
        print(
            f"{j['label']:<14} 基線 {j['baseline_size']:>2} 站｜"
            f"平均 {j['mean_size']:.1f} 站｜相似度 {j['jaccard_mean']:.2f}"
            f"（最差 5% {j['jaccard_p05']:.2f}）｜完全一致 {j['identical_rate']:.1%}"
        )

    cells1 = {(r["station_id"], r["dim"]) for r in rows if r["flip_plus1"] or r["flip_minus1"]}
    combos1 = sum(1 for r in rows if r["flip_plus1"] or r["flip_minus1"])
    combos2 = sum(
        1
        for r in rows
        if (r["flip_plus2"] or r["flip_minus2"]) and not (r["flip_plus1"] or r["flip_minus1"])
    )
    stations = {sid for sid, _ in cells1}
    print(f"\n一級擾動即翻轉：{combos1} / {len(rows)} 個「格 × 情境」組合")
    print(f"只錯兩級才翻轉：{combos2} / {len(rows)}")
    print(f"涉及格數：{len(cells1)} / 136；涉及站數：{len(stations)} / 17")

    if args.csv:
        import csv

        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n逐格結果：{args.csv}")

    report = summarize(payload, joints, rows)

    if args.fix_fragile:
        fragile: dict[str, set] = {}
        for r in rows:
            if r["flip_plus1"] or r["flip_minus1"]:
                fragile.setdefault(r["scenario"], set()).add((r["station_id"], r["dim"]))
        known = [joint_runs(payload, s, args.runs, rng, fragile.get(s.label, set())) for s in scenarios]

        print("\n=== 假設脆弱格已實測（其餘照舊扰动）===")
        print("| 情境 | 固定格數 | 複核前一致率 | 複核後一致率 | 提升 |")
        extra_lines = [
            "\n## 四、假設一級脆弱格已實測之後\n",
            "把各情境中「錯一級就翻轉」的格當作已現場量準（固定不擾動），其餘 124 格照舊有不確定性，重跑同一組抽樣：\n",
            "| 情境 | 固定格數 | 複核前完全一致 | 複核後完全一致 | 提升 |",
            "|---|---|---|---|---|",
        ]
        for base_j, known_j in zip(joints, known):
            n = len(fragile.get(base_j["label"], set()))
            gain = known_j["identical_rate"] - base_j["identical_rate"]
            print(
                f"{base_j['label']:<14} 固定 {n:>2} 格｜"
                f"{base_j['identical_rate']:.1%} → {known_j['identical_rate']:.1%}"
                f"（{gain:+.1%}）｜相似度 {base_j['jaccard_mean']:.2f} → {known_j['jaccard_mean']:.2f}"
            )
            extra_lines.append(
                f"| {base_j['label']} | {n} | {base_j['identical_rate']:.1%} | "
                f"{known_j['identical_rate']:.1%} | {gain:+.1%} |"
            )
        extra_lines.append(
            "\n> 「固定」只是模擬手法：假設這些格為真值、不再擾動，並不代表真實數值已知。"
            "若實際量到的值與現值差一級以上，這一節的結論需要重算。"
        )
        report = report + "\n" + "\n".join(extra_lines)

    if args.markdown:
        Path(args.markdown).write_text(report, encoding="utf-8")
        print(f"摘要報告：{args.markdown}")
    else:
        print("\n" + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
