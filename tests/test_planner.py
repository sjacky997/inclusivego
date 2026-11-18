"""求解器不變量測試。每一條都對應方案裡承諾過的行為。

執行：python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import copy
import itertools
import random
import time
import unittest
from pathlib import Path

from solver.planner import (
    DIMS,
    ZONE_ORDER,
    Preferences,
    expected_minutes,
    load_facilities,
    plan,
)

DATA = load_facilities()
FACILITIES = DATA["facilities"]
BY_ID = {item["id"]: item for item in FACILITIES}


class TestHardConstraints(unittest.TestCase):
    def test_all_facilities_when_budget_is_generous(self):
        result = plan(DATA, Preferences(budget_min=600, triggers=(), rest_interval=0))
        self.assertEqual(len(result.stops), 17)
        self.assertEqual(len({s.id for s in result.stops}), 17)

    def test_avoid_high_removes_only_those_with_high_level(self):
        prefs = Preferences(budget_min=600, triggers=("sound",), handling="avoid-high", rest_interval=0)
        result = plan(DATA, prefs)
        for stop in result.stops:
            self.assertLess(BY_ID[stop.id]["sensory"]["sound"], 5, f"{stop.name} 不應入選")
        for item in result.excluded:
            self.assertGreaterEqual(BY_ID[item["id"]]["sensory"]["sound"], 5)

    def test_avoid_medium_is_stricter_than_avoid_high(self):
        # 現有 17 站沒有 4 級，用合成站證明 avoid-medium（剔 4 以上）比 avoid-high（剔 5）嚴
        payload = TestSensoryThreshold._payload_with_level_four()
        high = plan(payload, Preferences(budget_min=900, triggers=("crowd",), handling="avoid-high", rest_interval=0))
        medium = plan(payload, Preferences(budget_min=900, triggers=("crowd",), handling="avoid-medium", rest_interval=0))
        self.assertIn("synthetic_level_four", {s.id for s in high.stops})
        self.assertNotIn("synthetic_level_four", {s.id for s in medium.stops})

    def test_warn_only_keeps_high_stimulation(self):
        prefs = Preferences(budget_min=600, triggers=("sound",), handling="warn-only", rest_interval=0)
        result = plan(DATA, prefs)
        self.assertEqual(len(result.stops), 17)
        self.assertFalse(result.excluded)
        self.assertTrue(any("高刺激" in w for w in result.warnings))

    def test_excluded_never_appear_in_route(self):
        prefs = Preferences(budget_min=240, triggers=("sound", "crowd"), handling="avoid-high")
        result = plan(DATA, prefs)
        excluded_ids = {item["id"] for item in result.excluded}
        for stop in result.stops:
            self.assertNotIn(stop.id, excluded_ids)


class TestInvariants(unittest.TestCase):
    def test_planned_minutes_never_exceed_budget(self):
        random.seed(7)
        for _ in range(300):
            triggers = tuple(random.sample(DIMS, random.randint(0, 3)))
            prefs = Preferences(
                budget_min=random.choice([60, 120, 180, 240, 420, 600]),
                triggers=triggers,
                handling=random.choice(["avoid-high", "avoid-medium", "warn-only", "decide-later"]),
                rest_interval=random.choice([0, 30, 45, 60]),
                priority=random.choice(["low-stimulation", "less-walking", "more-interest"]),
                meal=random.choice(["none", "snack", "meal", "own"]),
            )
            result = plan(DATA, prefs)
            self.assertLessEqual(
                round(result.planned_min, 1), prefs.budget_min,
                f"超出預算：{result.planned_min} > {prefs.budget_min}（{prefs}）",
            )

    def test_no_duplicate_stops(self):
        result = plan(DATA, Preferences(budget_min=420, triggers=("light",), rest_interval=45, meal="snack"))
        ids = [stop.id for stop in result.stops]
        self.assertEqual(len(ids), len(set(ids)))

    def test_zone_order_is_monotonic(self):
        result = plan(DATA, Preferences(budget_min=600, triggers=(), rest_interval=0))
        indexes = [ZONE_ORDER.index(stop.zone) for stop in result.stops]
        self.assertEqual(indexes, sorted(indexes))

    def test_duration_range_matches_selection(self):
        result = plan(DATA, Preferences(budget_min=240, triggers=("light",), rest_interval=0))
        expected_low = sum(BY_ID[s.id]["duration"]["min"] for s in result.stops)
        expected_high = sum(BY_ID[s.id]["duration"]["max"] for s in result.stops)
        self.assertEqual(result.total_min, expected_low)
        self.assertEqual(result.total_max, expected_high)

    def test_same_input_same_output(self):
        prefs = Preferences(budget_min=240, triggers=("crowd",), handling="avoid-high", rest_interval=45, meal="snack")
        first = plan(DATA, prefs).to_dict()
        second = plan(DATA, prefs).to_dict()
        self.assertEqual(first, second)
        self.assertEqual([s["id"] for s in first["stops"]], [s["id"] for s in second["stops"]])

    def test_tiny_budget_returns_empty_with_warning_or_stops(self):
        result = plan(DATA, Preferences(budget_min=30, triggers=("sound", "crowd", "light"), rest_interval=0))
        self.assertLessEqual(result.planned_min, 30)
        self.assertLessEqual(len(result.stops), 1)


class TestBreaks(unittest.TestCase):
    def test_rest_inserted_about_every_interval(self):
        prefs = Preferences(budget_min=600, triggers=(), rest_interval=45, meal="none")
        result = plan(DATA, prefs)
        self.assertTrue(result.breaks, "長行程應該有休息")
        self.assertTrue(all(block["type"] == "rest" for block in result.breaks))

    def test_no_rest_when_interval_zero(self):
        result = plan(DATA, Preferences(budget_min=600, triggers=(), rest_interval=0))
        self.assertFalse(result.breaks)

    def test_meal_only_when_food_street_selected(self):
        prefs = Preferences(budget_min=600, triggers=(), rest_interval=0, meal="meal")
        result = plan(DATA, prefs)
        names = [stop.name for stop in result.stops]
        meal_blocks = [block for block in result.breaks if block["type"] == "meal"]
        if any("老大街" in name for name in names):
            self.assertTrue(meal_blocks)
        else:
            self.assertFalse(meal_blocks)


class TestWalkTime(unittest.TestCase):
    """walk_min 進資料契約後，步行時間必須真的計入總時長，且可追溯到每一區。"""

    def test_every_facility_declares_walk_min(self):
        for item in FACILITIES:
            self.assertIn("walk_min", item, f"{item['name']} 缺 walk_min")
            self.assertIsInstance(item["walk_min"], int)
            self.assertGreaterEqual(item["walk_min"], 0)
            self.assertLessEqual(item["walk_min"], 15)

    def test_walk_min_grows_along_zone_order(self):
        for zone in ZONE_ORDER:
            ordered = sorted([f for f in FACILITIES if f["zone"] == zone], key=lambda f: f["legacy_rank"])
            values = [f["walk_min"] for f in ordered]
            self.assertEqual(values, sorted(values), f"{zone} 的 walk_min 應隨動線遞增")

    def test_walk_minutes_match_deepest_stop_per_zone(self):
        result = plan(DATA, Preferences(budget_min=240, triggers=("sound",), rest_interval=0))
        deepest = {}
        for stop in result.stops:
            deepest[stop.zone] = max(deepest.get(stop.zone, 0), BY_ID[stop.id]["walk_min"])
        expected = sum(deepest.values()) + 8 * (len(deepest) - 1)
        self.assertAlmostEqual(result.walk_min, expected, delta=0.01)
        self.assertEqual(result.to_dict()["walk_minutes"], expected)

    def test_planned_minutes_include_walk(self):
        result = plan(DATA, Preferences(budget_min=240, triggers=("sound",), rest_interval=45))
        stops_min = sum(expected_minutes(BY_ID[s.id]) for s in result.stops)
        breaks_min = sum(b["minutes"] for b in result.breaks)
        self.assertAlmostEqual(result.planned_min, stops_min + breaks_min + result.walk_min, delta=1.0)

    def test_farther_route_never_walks_less(self):
        near = plan(DATA, Preferences(budget_min=120, triggers=(), rest_interval=0))
        far = plan(DATA, Preferences(budget_min=600, triggers=(), rest_interval=0))
        self.assertGreater(far.walk_min, near.walk_min)


class TestZoneWalkSensitivity(unittest.TestCase):
    """跨區步行是假設值，必須可調；調大只會拉長總時長，不會縮短。"""

    def test_zone_walk_changes_walk_minutes(self):
        base = Preferences(budget_min=600, triggers=(), rest_interval=0, zone_walk=8)
        slow = Preferences(budget_min=600, triggers=(), rest_interval=0, zone_walk=12)
        fast = Preferences(budget_min=600, triggers=(), rest_interval=0, zone_walk=4)
        here = plan(DATA, base)
        slower = plan(DATA, slow)
        quicker = plan(DATA, fast)
        zones = len({s.zone for s in here.stops})
        delta = 4 * (zones - 1)
        self.assertAlmostEqual(slower.walk_min, here.walk_min + delta, delta=0.01)
        self.assertAlmostEqual(quicker.walk_min, here.walk_min - delta, delta=0.01)
        self.assertGreater(slower.planned_min, here.planned_min)

    def test_zone_walk_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            plan(DATA, Preferences(zone_walk=-3))
        with self.assertRaises(ValueError):
            plan(DATA, Preferences(zone_walk=99))


class TestEdgeCases(unittest.TestCase):
    def test_invalid_handling_rejected(self):
        with self.assertRaises(ValueError):
            plan(DATA, Preferences(handling="whatever"))

    def test_unknown_trigger_rejected(self):
        with self.assertRaises(ValueError):
            plan(DATA, Preferences(triggers=("temperature",)))

    def test_budget_too_small_rejected(self):
        with self.assertRaises(ValueError):
            plan(DATA, Preferences(budget_min=10))

    def test_all_dimensions_avoided_still_returns_something(self):
        prefs = Preferences(budget_min=240, triggers=tuple(DIMS), handling="avoid-medium")
        result = plan(DATA, prefs)
        self.assertLessEqual(result.planned_min, 240)


class TestPerformance(unittest.TestCase):
    def test_p95_under_50ms(self):
        durations = []
        prefs_pool = [
            Preferences(budget_min=240, triggers=("sound",), rest_interval=45, meal="snack"),
            Preferences(budget_min=420, triggers=("crowd", "light"), priority="more-interest"),
            Preferences(budget_min=120, triggers=("sound", "crowd", "light"), handling="avoid-medium"),
        ]
        for prefs in itertools.islice(itertools.cycle(prefs_pool), 60):
            start = time.perf_counter()
            plan(DATA, prefs)
            durations.append((time.perf_counter() - start) * 1000)
        durations.sort()
        p95 = durations[int(len(durations) * 0.95) - 1]
        self.assertLess(p95, 50, f"p95 = {p95:.1f} ms，超過 50 ms")


if __name__ == "__main__":
    unittest.main()


class TestSensoryThreshold(unittest.TestCase):
    """鎖住「1–5 名義五級、實務三級」下 avoid-medium 的門檻語義。"""

    @staticmethod
    def _payload_with_level_four() -> dict:
        base = copy.deepcopy(FACILITIES[0])
        base.update({
            "id": "synthetic_level_four",
            "name": "測試站（人群 4）",
            "sensory": {dim: 1 for dim in DIMS},
        })
        base["sensory"]["crowd"] = 4
        return {"facilities": FACILITIES + [base]}

    def test_level_three_kept_by_medium(self):
        # 改前：門檻 3 會把「中」也剔掉，只勾人群時只剩 4 站
        result = plan(DATA, Preferences(budget_min=240, triggers=("crowd",), handling="avoid-medium"))
        self.assertTrue(any(BY_ID[s.id]["sensory"]["crowd"] == 3 for s in result.stops),
                        "門檻改 4 之後，人群等級 3 的站應留在候選中")

    def test_light_trigger_no_longer_returns_empty_route(self):
        # 改前：light 只有 3 與 5，avoid-medium 以 3 為門檻會全數剔除，回傳 0 站
        result = plan(DATA, Preferences(budget_min=240, triggers=("light",), handling="avoid-medium"))
        self.assertGreater(len(result.stops), 0)
        for stop in result.stops:
            self.assertLessEqual(BY_ID[stop.id]["sensory"]["light"], 3)


class TestHandlingSemantics(unittest.TestCase):
    """鎖住 handling 的語義：decide-later 與 warn-only 選站相同，只差責任歸屬。

    介面若把 decide-later 寫成「已幫你處理」或「每站提供 Plan B」，就與此處契約不符。
    """

    PREFS = dict(budget_min=240, triggers=("sound", "crowd"), rest_interval=45)

    def _plan(self, handling):
        return plan(DATA, Preferences(handling=handling, **self.PREFS))

    def test_decide_later_selects_same_stops_as_warn_only(self):
        a = self._plan("warn-only")
        b = self._plan("decide-later")
        self.assertEqual([s.id for s in a.stops], [s.id for s in b.stops])
        self.assertEqual(a.planned_min, b.planned_min)

    def test_decide_later_excludes_nothing(self):
        result = self._plan("decide-later")
        self.assertEqual(result.excluded, [], "decide-later 不得剔除任何站，剔除只由硬約束負責")

    def test_decide_later_flags_without_excluding(self):
        result = self._plan("decide-later")
        flagged = [
            s for s in result.stops
            if any(BY_ID[s.id]["sensory"][d] >= 5 for d in self.PREFS["triggers"])
        ]
        self.assertTrue(flagged, "此情境應存在高刺激站，否則測試失去意義")
        joined = "".join(result.warnings)
        self.assertIn("請自行決定", joined)
        for stop in flagged:
            self.assertIn(stop.name, joined)

    def test_warn_only_and_decide_later_wording_differs(self):
        a = self._plan("warn-only")
        b = self._plan("decide-later")
        self.assertNotEqual(a.warnings, b.warnings, "兩種模式的提示必須可區分，否則等於同一個選項")

    def test_decide_later_without_triggers_is_silent(self):
        result = plan(DATA, Preferences(budget_min=420, triggers=(), handling="decide-later"))
        self.assertEqual(result.excluded, [])
        self.assertFalse(
            [w for w in result.warnings if "請自行決定" in w],
            "未勾選任何觸發維度時，不應出現待決策提示",
        )
