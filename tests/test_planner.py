"""求解器不變量測試。每一條都對應方案裡承諾過的行為。

執行：python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

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
        high = plan(DATA, Preferences(budget_min=600, triggers=("crowd",), handling="avoid-high"))
        medium = plan(DATA, Preferences(budget_min=600, triggers=("crowd",), handling="avoid-medium"))
        self.assertLess(len(medium.stops), len(high.stops))

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
