"""行程求解器：在時間預算與感官約束下，產生可解釋的遊覽路線。

設計原則
    1. 硬約束先篩選，不可違反（避開的感官維度直接剔除景點）。
    2. 區域固定順序（正門外 → 夢幻水都 → 亞洲動物天地 → 威威天地），不可跳區回頭。
    3. 每區站點 ≤ 8，以子集列舉求區內最優，再跨區做時間分配的動態規劃。
    4. 休息與用餐是硬約束，插入後若超預算，寧可少去一站。
    5. 同輸入必得同輸出（平手以 id 字典序決定）。

用法
    python3 -m solver.planner --budget 240 --avoid sound,crowd --handling avoid-high
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "facilities.json"

ZONE_ORDER = ["正門外", "夢幻水都", "亞洲動物天地", "威威天地"]
DIMS = ["sound", "light", "crowd", "enclosed", "smell", "cold", "wet", "motion"]
DIM_LABELS = {"sound": "聲音", "light": "光線", "crowd": "人群", "enclosed": "封閉感",
              "smell": "氣味", "cold": "低溫", "wet": "濕滑", "motion": "動態"}
LEVEL_NAMES = {1: "低", 2: "偏低", 3: "中", 4: "偏高", 5: "高"}

WALK_BETWEEN_ZONES_MIN = 8      # 相鄰區域步行時間，假設值
REST_MINUTES = 15               # 每次休息長度
MEAL_MINUTES = {"none": 0, "snack": 15, "meal": 40, "own": 20}

# 硬約束門檻：avoid-high 剔除 5，avoid-medium 剔徐 3 以上
AVOID_THRESHOLD = {"avoid-high": 5, "avoid-medium": 3}


@dataclass(frozen=True)
class Preferences:
    budget_min: int = 240
    triggers: tuple[str, ...] = ()
    handling: str = "avoid-high"       # avoid-high | avoid-medium | warn-only | decide-later
    rest_interval: int = 45            # 0 代表不需要
    priority: str = "low-stimulation"  # low-stimulation | less-walking | more-interest
    meal: str = "none"

    def validate(self) -> None:
        if self.budget_min < 30:
            raise ValueError("時間預算至少 30 分鐘")
        if self.handling not in {"avoid-high", "avoid-medium", "warn-only", "decide-later"}:
            raise ValueError(f"未知的 handling：{self.handling}")
        if self.priority not in {"low-stimulation", "less-walking", "more-interest"}:
            raise ValueError(f"未知的 priority：{self.priority}")
        if self.meal not in MEAL_MINUTES:
            raise ValueError(f"未知的 meal：{self.meal}")
        unknown = [t for t in self.triggers if t not in DIMS]
        if unknown:
            raise ValueError(f"未知的感官維度：{unknown}")


@dataclass
class Stop:
    id: str
    name: str
    zone: str
    minutes: float
    score: float
    walk_min: int = 0
    reason: str = ""
    excluded: bool = False
    exclude_reason: str = ""


@dataclass
class Plan:
    stops: list[Stop] = field(default_factory=list)
    breaks: list[dict] = field(default_factory=list)
    total_min: float = 0.0
    total_max: float = 0.0
    planned_min: float = 0.0
    walk_min: float = 0.0
    warnings: list[str] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    transitions: int = 0

    def to_dict(self) -> dict:
        return {
            "stops": [
                {
                    "id": s.id,
                    "name": s.name,
                    "zone": s.zone,
                    "minutes": round(s.minutes, 1),
                    "reason": s.reason,
                }
                for s in self.stops
            ],
            "breaks": self.breaks,
            "planned_minutes": round(self.planned_min, 1),
            "walk_minutes": round(self.walk_min, 1),
            "duration_range": [round(self.total_min, 1), round(self.total_max, 1)],
            "warnings": self.warnings,
            "excluded": self.excluded,
        }


def expected_minutes(item: dict) -> float:
    d = item["duration"]
    return (d["min"] + d["max"]) / 2


def load_facilities(path: Path = DEFAULT_DATA) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sensory_penalty(item: dict, prefs: Preferences) -> float:
    if not prefs.triggers:
        return 0.0
    values = [item["sensory"][dim] for dim in prefs.triggers]
    return sum(values) / len(values)


def _score(item: dict, prefs: Preferences) -> float:
    """每一站的基本價值必須為正，否則「warn-only」會把高刺激景點算成負資產而變相排除。

    感官值只是調整排序，不應改變「去不去」的判斷——那由硬約束負責。
    """
    penalty = _sensory_penalty(item, prefs)

    if prefs.priority == "low-stimulation":
        return 8.0 - 1.2 * penalty
    if prefs.priority == "more-interest":
        return 12.0 - 0.8 * penalty
    # less-walking：每站價值較低，讓同分時偏好較少站點
    return 6.0 - 1.0 * penalty


def build_candidates(facilities: list[dict], prefs: Preferences) -> dict[str, list[Stop]]:
    by_zone: dict[str, list[Stop]] = {zone: [] for zone in ZONE_ORDER}

    for item in facilities:
        zone = item["zone"]
        threshold = AVOID_THRESHOLD.get(prefs.handling)

        if threshold is not None and prefs.triggers:
            hits = [
                f"{DIM_LABELS.get(dim, dim)} {LEVEL_NAMES.get(item['sensory'][dim], item['sensory'][dim])}"
                for dim in prefs.triggers
                if item["sensory"][dim] >= threshold
            ]
            if hits:
                by_zone[zone].append(Stop(
                    id=item["id"], name=item["name"], zone=zone,
                    minutes=expected_minutes(item), score=0.0,
                    excluded=True,
                    exclude_reason="；".join(hits) + " 超出可接受門檻",
                    walk_min=item.get("walk_min", 0),
                ))
                continue

        by_zone[zone].append(Stop(
            id=item["id"], name=item["name"], zone=zone,
            minutes=expected_minutes(item),
            score=_score(item, prefs),
            walk_min=item.get("walk_min", 0),
        ))
    return by_zone


def _pareto(options: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """保留 (時間, 分數) 的帕雷托前緣：時間更長但分數更低者無意義。"""
    options.sort(key=lambda pair: (pair[0], -pair[1]))
    kept: list[tuple[int, float]] = []
    best = -math.inf
    for minutes, score in options:
        if score > best:
            kept.append((minutes, score))
            best = score
    return kept


def _zone_options(stops: list[Stop], prefs: Preferences) -> dict[int, tuple[int, float]]:
    """列舉區內所有子集，回傳 {(minutes, score): mask} 的帕雷托集合。"""
    usable = [s for s in stops if not s.excluded]
    pool = list(range(len(usable)))
    raw: dict[tuple[int, float], int] = {}
    for mask in range(1, 1 << len(pool)):
        minutes = 0
        score = 0.0
        walk = 0
        for bit, index in enumerate(pool):
            if mask >> bit & 1:
                minutes += int(round(usable[index].minutes))
                score += usable[index].score
                walk = max(walk, usable[index].walk_min)
        # 區內按固定動線走，走到最深一站即已步行完該區
        raw[(minutes + walk, round(score, 3))] = mask

    points = sorted(raw, key=lambda p: (p[0], -p[1]))
    kept: list[tuple[int, float]] = []
    best = -math.inf
    for point in points:
        if point[1] > best:
            kept.append(point)
            best = point[1]
    return {point: raw[point] for point in kept}


def _dp_choose(by_zone: dict[str, list[Stop]], prefs: Preferences) -> tuple[list[Stop], list[str], int]:
    """跨區時間分配：dp[已用分鐘] = (分數, 每區選中 mask)。"""
    dp: dict[int, tuple[float, dict[str, int]]] = {0: (0.0, {})}
    transitions = 0

    for zone in ZONE_ORDER:
        stops = by_zone.get(zone, [])
        if not stops:
            continue
        options = _zone_options(stops, prefs)
        if not options:
            continue
        next_dp: dict[int, tuple[float, dict[str, int]]] = {}
        for used, (score, chosen) in dp.items():
            for (minutes, gain), mask in options.items():
                walk = WALK_BETWEEN_ZONES_MIN if chosen else 0
                total = used + minutes + walk
                transitions += 1
                if total > prefs.budget_min - _fixed_reserve(prefs):
                    continue
                candidate = (score + gain, {**chosen, zone: mask})
                if total not in next_dp or candidate[0] > next_dp[total][0] + 1e-9:
                    next_dp[total] = candidate
        # 保留每個時間點的最佳解，並移除被支配者
        best_so_far = -math.inf
        pruned: dict[int, tuple[float, dict[str, int]]] = {}
        for used in sorted(next_dp):
            if next_dp[used][0] > best_so_far + 1e-9:
                pruned[used] = next_dp[used]
                best_so_far = next_dp[used][0]
        dp = pruned

    best_used = None
    best_score = -math.inf
    for used, (score, chosen) in dp.items():
        if score > best_score + 1e-9 or (abs(score - best_score) < 1e-9 and best_used is not None and used < best_used):
            best_score, best_used, best_choice = score, used, chosen
    if best_used is None:
        return [], [f"預算 {prefs.budget_min} 分鐘不足以完成任何一站"], transitions

    chosen_stops: list[Stop] = []
    for zone in ZONE_ORDER:
        mask = best_choice.get(zone, 0)
        usable = [s for s in by_zone[zone] if not s.excluded]
        for bit, stop in enumerate(usable):
            if mask >> bit & 1:
                chosen_stops.append(stop)
    return chosen_stops, [], transitions


def walk_minutes(stops: list[Stop]) -> float:
    """各區走到最深一站的累計步行，加上跨區轉移。"""
    if not stops:
        return 0.0
    deepest: dict[str, int] = {}
    for stop in stops:
        deepest[stop.zone] = max(deepest.get(stop.zone, 0), stop.walk_min)
    return float(sum(deepest.values()) + WALK_BETWEEN_ZONES_MIN * (len(deepest) - 1))


def _fixed_reserve(prefs: Preferences) -> int:
    return MEAL_MINUTES.get(prefs.meal, 0)


def _describe(stop: Stop, prefs: Preferences, item: dict) -> str:
    if prefs.triggers:
        values = "、".join(f"{DIM_LABELS.get(dim, dim)} {LEVEL_NAMES.get(item['sensory'][dim], item['sensory'][dim])}" for dim in prefs.triggers)
        return f"符合你的感官設定（{values}）；預留 {int(round(stop.minutes))} 分鐘"
    return f"預留 {int(round(stop.minutes))} 分鐘"


def insert_breaks(stops: list[Stop], prefs: Preferences) -> list[dict]:
    """每 rest_interval 分鐘插入休息；用餐獨立成一個區塊。"""
    if not stops:
        return []
    blocks: list[dict] = []
    elapsed = 0.0
    since_rest = 0.0

    for stop in stops:
        if prefs.meal != "none" and prefs.meal != "own" and "老大街" in stop.name:
            blocks.append({"type": "meal", "after": stop.name, "minutes": MEAL_MINUTES[prefs.meal]})
            elapsed += MEAL_MINUTES[prefs.meal]
        elapsed += stop.minutes
        since_rest += stop.minutes

        if prefs.rest_interval and since_rest >= prefs.rest_interval:
            blocks.append({"type": "rest", "after": stop.name, "minutes": REST_MINUTES})
            elapsed += REST_MINUTES
            since_rest = 0.0
    return blocks


def plan(payload: dict, prefs: Preferences) -> Plan:
    prefs.validate()
    result = Plan()
    facilities = payload["facilities"]
    by_zone = build_candidates(facilities, prefs)

    for zone, stops in by_zone.items():
        for stop in stops:
            if stop.excluded:
                result.excluded.append({
                    "id": stop.id, "name": stop.name, "zone": zone,
                    "reason": stop.exclude_reason,
                })

    chosen, warnings, transitions = _dp_choose(by_zone, prefs)
    result.warnings.extend(warnings)
    result.transitions = transitions

    if not chosen:
        return result

    items = {item["id"]: item for item in facilities}
    for stop in chosen:
        stop.reason = _describe(stop, prefs, items[stop.id])

    total_expected = sum(s.minutes for s in chosen)
    result.total_min = sum(items[s.id]["duration"]["min"] for s in chosen)
    result.total_max = sum(items[s.id]["duration"]["max"] for s in chosen)

    blocks = insert_breaks(chosen, prefs)
    break_minutes = sum(b["minutes"] for b in blocks)
    walk = walk_minutes(chosen)
    planned = total_expected + break_minutes + walk

    # 硬約束：插休息/用餐後仍須在預算內，超出則由隊尾移除
    while planned > prefs.budget_min and len(chosen) > 1:
        dropped = chosen.pop()
        result.warnings.append(f"時間不足，已移除 {dropped.name}")
        total_expected = sum(s.minutes for s in chosen)
        blocks = insert_breaks(chosen, prefs)
        break_minutes = sum(b["minutes"] for b in blocks)
        walk = walk_minutes(chosen)
        planned = total_expected + break_minutes + walk

    result.stops = sorted(chosen, key=lambda s: (ZONE_ORDER.index(s.zone), -s.score, s.id))
    result.planned_min = planned
    result.walk_min = walk
    result.total_min = sum(items[s.id]["duration"]["min"] for s in result.stops)
    result.total_max = sum(items[s.id]["duration"]["max"] for s in result.stops)
    result.breaks = blocks

    if prefs.handling == "warn-only":
        risky = [s.name for s in chosen if prefs.triggers and any(items[s.id]["sensory"][d] >= 5 for d in prefs.triggers)]
        if risky:
            result.warnings.append("以下景點有高刺激但已保留：" + "、".join(risky))
    if prefs.meal == "own":
        result.warnings.append("自備食物：需自行安排用餐地點，未預留固定餐桌時間")

    if result.total_max > prefs.budget_min:
        result.warnings.append(
            f"最壞情況約 {int(result.total_max)} 分鐘，略超 {prefs.budget_min} 分鐘預算，現場需留意"
        )
    return result


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="InclusiveGo 行程求解器")
    parser.add_argument("--budget", type=int, default=240, help="時間預算（分鐘）")
    parser.add_argument("--avoid", default="", help="要避開的感官維度，逗號分隔")
    parser.add_argument("--handling", default="avoid-high", choices=list(AVOID_THRESHOLD) + ["warn-only", "decide-later"])
    parser.add_argument("--rest", type=int, default=45, help="休息間隔（分鐘），0 代表不需要")
    parser.add_argument("--priority", default="low-stimulation", choices=["low-stimulation", "less-walking", "more-interest"])
    parser.add_argument("--meal", default="none", choices=list(MEAL_MINUTES))
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    prefs = Preferences(
        budget_min=args.budget,
        triggers=tuple(t.strip() for t in args.avoid.split(",") if t.strip()),
        handling=args.handling,
        rest_interval=args.rest,
        priority=args.priority,
        meal=args.meal,
    )
    payload = load_facilities()
    result = plan(payload, prefs)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"預算 {prefs.budget_min} 分鐘｜避開 {prefs.triggers or '無'}｜{prefs.handling}｜休息每 {prefs.rest_interval} 分鐘")
    print(f"選中 {len(result.stops)} 站，預計 {int(result.planned_min)} 分鐘（停留範圍 {int(result.total_min)}-{int(result.total_max)}，步行 {int(result.walk_min)} 分鐘）")
    print("")
    for index, stop in enumerate(result.stops, 1):
        print(f"{index:>2}. [{stop.zone}] {stop.name}　{int(round(stop.minutes))} 分鐘")
        print(f"    理由：{stop.reason}")
    if result.breaks:
        print("")
        for block in result.breaks:
            label = "休息" if block["type"] == "rest" else "用餐"
            print(f"   + {label} {block['minutes']} 分鐘（{block['after']} 之後）")
    if result.warnings:
        print("")
        for warning in result.warnings:
            print(f"  ! {warning}")
    if result.excluded:
        print("")
        print(f"因感官設定排除 {len(result.excluded)} 站：")
        for item in result.excluded:
            print(f"   - {item['name']}：{item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
