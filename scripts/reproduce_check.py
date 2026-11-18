"""固定輸入重跑求解器，比對輸出雜湊，證明結果可重現。

用途：附錄 C「任何人拿到儲存庫與指令，能在自己的機器得到同一組數字」的機器可執行版本。
兩組 payload 覆蓋兩種極端：短預算＋單一觸發、全日＋無觸發＋用餐。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from solver.planner import Preferences, load_facilities, plan  # noqa: E402

EXPECTED = Path(__file__).with_name("expected_hashes.json")

CASES = [
    ("兩小時／避聲音／走 8 分鐘", dict(budget_min=120, triggers=("sound",), rest_interval=45)),
    ("全日／不設避開／走 10 分鐘", dict(budget_min=420, triggers=(), rest_interval=45, meal="snack", zone_walk=10)),
]


def run_case(keyword: str, kwargs: dict) -> tuple[str, dict]:
    result = plan(load_facilities(), Preferences(**kwargs)).to_dict()
    blob = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), result


def main() -> int:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    failures = 0
    for name, kwargs in CASES:
        digest, result = run_case(name, kwargs)
        stops = "、".join(s["name"] for s in result["stops"]) or "（無）"
        print(f"[{name}]")
        print(f"  站數 {len(result['stops'])}：{stops}")
        print(f"  停留＋步行＋休息＝{result['planned_minutes']} 分鐘（步行 {result['walk_minutes']}）")
        print(f"  sha256 {digest}")
        want = expected.get(name)
        if want is None:
            print("  尚未記錄預期雜湊，請把上面這行寫入 expected_hashes.json")
            failures += 1
        elif want == digest:
            print("  與預期一致")
        else:
            print(f"  與預期不一致，預期 {want}")
            failures += 1
    print(f"\n結果：{len(CASES) - failures}/{len(CASES)} 組一致")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
