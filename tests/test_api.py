"""端點測試：確認 /api/plan 真的回傳可用路線，且靜態檔案仍正常。

執行：python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

from serve import ROOT, InclusiveGoHandler


class QuietHandler(InclusiveGoHandler):
    def log_message(self, *args) -> None:  # 測試時不需要逐條請求日誌
        return


class TestPlanApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, payload: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/plan",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_returns_plan_within_budget(self) -> None:
        status, data = self.post({"budget_min": 120, "triggers": ["sound"], "handling": "avoid-high", "rest_interval": 45})
        self.assertEqual(status, 200)
        self.assertIn("stops", data)
        self.assertLessEqual(data["planned_minutes"], 120)
        self.assertLessEqual(data["duration_range"][0], data["duration_range"][1])
        for stop in data["stops"]:
            self.assertIn("reason", stop)
            self.assertTrue(stop["reason"])

    def test_candidates_limit_the_search_space(self) -> None:
        wanted = ["海洋奇觀", "百草生態徑", "砵砵火車頭"]
        status, data = self.post({"budget_min": 600, "candidates": wanted, "rest_interval": 0})
        self.assertEqual(status, 200)
        names = {stop["name"] for stop in data["stops"]}
        self.assertTrue(names.issubset(set(wanted)))
        self.assertTrue(names)

    def test_unknown_handling_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post({"handling": "no-such-mode"})
        self.assertEqual(ctx.exception.code, 400)

    def test_unknown_path_is_not_found(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/plan2",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 404)

    def test_static_data_still_served(self) -> None:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/data/facilities.json", timeout=5) as response:
            self.assertEqual(response.status, 200)
            pack = json.loads(response.read())
        self.assertEqual(len(pack["facilities"]), 17)


class TestAccessDisclosure(unittest.TestCase):
    """access 五欄在資料中全為 null，介面必須明示「未確認」，不得默默當成可用。"""

    ACCESS_KEYS = {"step_free", "quiet_room", "queue_required", "exit_ease", "staff_interaction"}

    def test_every_access_field_is_still_unknown(self) -> None:
        pack = json.loads((ROOT / "data" / "facilities.json").read_text(encoding="utf-8"))
        for item in pack["facilities"]:
            self.assertEqual(set(item["access"]), self.ACCESS_KEYS, f"{item['name']} 的 access 欄位不齊")
            for key in self.ACCESS_KEYS:
                self.assertIsNone(item["access"][key], f"{item['name']} 的 {key} 未核實卻填了值")

    def test_ui_discloses_unknown_access(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("未確認", html)
        self.assertIn("function accessRow(", html)
        self.assertIn("無障礙資訊", html)
        for key in self.ACCESS_KEYS:
            self.assertIn(key, html, f"介面未列出 {key}")


if __name__ == "__main__":
    unittest.main()
