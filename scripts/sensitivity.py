"""敏感度分析：同一個情境，只改「跨區步行」假設值，看選站結果會不會變。

用途
    8 分鐘是假設值，沒有實測。與其辯論它準不準，不如證明結論對它不敏感：
    若 4／6／8／10／12 分鐘下選出的站點完全相同，路線就站得住腳。

用法
    python3 scripts/sensitivity.py                 # 三個內建情境
    python3 scripts/sensitivity.py --values 4,8,12
    python3 scripts/sensitivity.py --budget 420 --avoid "" --rest 45
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver.planner import Preferences, load_facilities, plan  # noqa: E402

VALUES = (4, 6, 8, 10, 12)


def width(text: str) -> int:
    """東亞全形字算 2 格，讓表格在終端機對齊。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, size: int) -> str:
    return text + " " * max(0, size - width(text))


def run_case(data: dict, prefs: Preferences) -> dict:
    result = plan(data, prefs)
    return {
        "stops": [s.name for s in result.stops],
        "count": len(result.stops),
        "walk": round(result.walk_min, 1),
        "planned": round(result.planned_min, 1),
    }


def table(data: dict, label: str, prefs: Preferences, values=VALUES) -> tuple[list[str], str]:
    rows = []
    baseline = None
    for value in values:
        case = run_case(data, Preferences(**{**prefs.__dict__, "zone_walk": value}))
        rows.append((value, case))
        if value == 8:
            baseline = case

    header = f"情境：{label}｜預算 {prefs.budget_min} 分鐘｜避開 {'、'.join(prefs.triggers) or '無'}｜{prefs.handling}｜休息每 {prefs.rest_interval} 分鐘"
    lines = [header, ""]
    cols = [("跨區步行", 10), ("站數", 6), ("步行", 8), ("合計", 8), ("與 8 分鐘相比", 0)]
    lines.append("| " + " | ".join(pad(name, size) if size else name for name, size in cols) + " |")
    lines.append("|" + "|".join("-" * 8 for _ in cols) + "|")

    for value, case in rows:
        if baseline is None:
            verdict = "（基準）"
        elif case["stops"] == baseline["stops"]:
            verdict = "選站相同"
        else:
            only_new = [n for n in case["stops"] if n not in baseline["stops"]]
            only_lost = [n for n in baseline["stops"] if n not in case["stops"]]
            bits = []
            if only_lost:
                bits.append(f"少（{'、'.join(only_lost)}）")
            if only_new:
                bits.append(f"多（{'、'.join(only_new)}）")
            verdict = ("換站：" if case["count"] == baseline["count"] else "；".join(bits) + " " ) + "；".join(bits) if bits else "次序不同"
        lines.append(
            "| " + " | ".join([
                pad(f"{value} 分鐘", 10),
                pad(str(case["count"]), 6),
                pad(f"{case['walk']:.0f} 分", 8),
                pad(f"{case['planned']:.0f} 分", 8),
                verdict,
            ]) + " |"
        )

    if baseline is None:
        return lines, "未測試 8 分鐘基準，無法判斷敏感度。"

    index = [v for v, _ in rows].index(8)
    low = high = index
    while low - 1 >= 0 and rows[low - 1][1]["stops"] == baseline["stops"]:
        low -= 1
    while high + 1 < len(rows) and rows[high + 1][1]["stops"] == baseline["stops"]:
        high += 1

    stable = f"{rows[low][0]}–{rows[high][0]} 分鐘" if low != high else f"{rows[low][0]} 分鐘"
    changed = [(v, case) for v, case in rows if case["stops"] != baseline["stops"]]

    if not changed:
        summary = f"結論：{values[0]}–{values[-1]} 分鐘區間內選站完全相同，路線對此假設不敏感。"
    elif not (low == 0 and high == len(rows) - 1):
        def describe(value, case):
            delta = len(case["stops"]) - baseline["count"]
            if delta > 0:
                return f"{value} 分鐘多 {delta} 站"
            if delta < 0:
                return f"{value} 分鐘少 {-delta} 站"
            return f"{value} 分鐘換站"

        detail = "；".join(describe(v, case) for v, case in changed)
        summary = (
            f"結論：{stable}（含 8 分鐘基準）選站不變；{detail}。"
            "即假設只要不高於 8 分鐘，路線不受影響。"
        )
    else:
        summary = "結論：選站隨假設改變，需在文件中逐值交代。"
    return lines, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="跨區步行假設值的敏感度分析")
    parser.add_argument("--values", default=",".join(str(v) for v in VALUES), help="要比較的假設值，逗號分隔")
    parser.add_argument("--budget", type=int, default=None, help="只跑單一自訂情境")
    parser.add_argument("--avoid", default="", help="感官維度，逗號分隔")
    parser.add_argument("--handling", default="avoid-high")
    parser.add_argument("--rest", type=int, default=45)
    parser.add_argument("--meal", default="none")
    args = parser.parse_args(argv)

    values = tuple(int(v) for v in args.values.split(",") if v.strip())
    data = load_facilities()

    if args.budget:
        scenarios = [(
            "自訂",
            Preferences(budget_min=args.budget,
                        triggers=tuple(t.strip() for t in args.avoid.split(",") if t.strip()),
                        handling=args.handling, rest_interval=args.rest, meal=args.meal),
        )]
    else:
        scenarios = [
            ("2 小時／避聲音", Preferences(budget_min=120, triggers=("sound",), rest_interval=45)),
            ("半日／避人群", Preferences(budget_min=240, triggers=("crowd",), rest_interval=45)),
            ("全日／不設避開", Preferences(budget_min=420, triggers=(), rest_interval=45, meal="snack")),
        ]

    summaries = []
    for label, prefs in scenarios:
        lines, summary = table(data, label, prefs, values)
        print("\n".join(lines))
        print("")
        summaries.append(f"- {label}：{summary}")
        print(summary)
        print("")

    print("總結")
    for line in summaries:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
