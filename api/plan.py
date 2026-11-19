"""Vercel Python 函數：POST /api/plan -> 求解器結果。

與 serve.py 共用同一套 solver/planner.py，差別只在運算環境。
"""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solver.planner import Preferences, load_facilities, plan  # noqa: E402


def _prefs(payload: dict) -> Preferences:
    return Preferences(
        budget_min=int(payload.get("budget_min") or 240),
        triggers=tuple(payload.get("triggers") or ()),
        handling=payload.get("handling") or "avoid-high",
        rest_interval=int(payload.get("rest_interval") or 0),
        priority=payload.get("priority") or "low-stimulation",
        meal=payload.get("meal") or "none",
        zone_walk=int(payload.get("zone_walk") or 8),
    )


def _compute(payload: dict) -> dict:
    prefs = _prefs(payload)
    pack = load_facilities(ROOT / "data" / "facilities.json")

    wanted = [str(n).strip() for n in (payload.get("candidates") or []) if str(n).strip()]
    if wanted:
        allowed = set(wanted)
        pack = {**pack, "facilities": [f for f in pack["facilities"] if f["name"] in allowed]}
        if not pack["facilities"]:
            raise ValueError("候選景點全部不在資料契約內")

    return plan(pack, prefs).to_dict()


class handler(BaseHTTPRequestHandler):
    server_version = "InclusiveGo/1.0"

    def do_POST(self):  # noqa: N802
        self._reply()

    def do_GET(self):  # noqa: N802
        self._json(405, {"error": "請用 POST 呼叫 /api/plan"})

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _reply(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            result = _compute(payload)
            self._json(200, result)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            self._json(400, {"error": f"請求格式不正確：{exc}"})
        except Exception as exc:  # 單次失敗不應讓整個函數崩潰
            self._json(500, {"error": f"求解器執行失敗：{exc}"})

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)
