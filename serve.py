"""Serve this static test package locally without third-party dependencies.

啟動前先驗證 data/facilities.json，資料不合格就不開站，避免用錯資料做 demo。
啟動後同時提供 POST /api/plan，由 solver/planner.py 計算路線，前端只負責顯示。

    python3 serve.py                # 先驗證，再開站
    python3 serve.py --skip-validate  # 跳過驗證（僅限緊急示範）
"""

import argparse
import json
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
import webbrowser

from solver.planner import Preferences, load_facilities, plan

ROOT = Path(__file__).resolve().parent
CANDIDATES = [ROOT / "scripts" / "validate.py", ROOT / "validate.py"]


def find_validator() -> Path | None:
    for path in CANDIDATES:
        if path.exists():
            return path
    return None


def run_validation() -> bool:
    validator = find_validator()
    if validator is None:
        print("找不到 validate.py，跳過資料驗證。", flush=True)
        return True

    print("正在驗證 data/facilities.json …", flush=True)
    result = subprocess.run([sys.executable, str(validator)], cwd=str(ROOT))

    if result.returncode == 0:
        print("資料驗證通過，啟動網站。\n", flush=True)
        return True

    if result.returncode == 2:
        print("\n無法執行驗證，通常是缺少套件。請先執行：", flush=True)
        print("    python3 -m pip install -r requirements.txt", flush=True)
    else:
        print("\n資料驗證失敗，已在上面列出錯誤位置。修正後再啟動：", flush=True)
        print("    python3 scripts/validate.py", flush=True)
        print("如確需暫時略過： python3 serve.py --skip-validate", flush=True)
    return False


class InclusiveGoHandler(SimpleHTTPRequestHandler):
    """靜態檔案 + 一個求解器端點。"""

    server_version = "InclusiveGo/1.0"

    def do_POST(self) -> None:  # noqa: N802（http.server 的命名約定）
        if self.path.split("?", 1)[0] != "/api/plan":
            self._send_json(404, {"error": "找不到這個端點"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(raw.decode("utf-8"))
            prefs = Preferences(
                budget_min=int(payload.get("budget_min") or 240),
                triggers=tuple(payload.get("triggers") or ()),
                handling=payload.get("handling") or "avoid-high",
                rest_interval=int(payload.get("rest_interval") or 0),
                priority=payload.get("priority") or "low-stimulation",
                meal=payload.get("meal") or "none",
            )
            pack = load_facilities(ROOT / "data" / "facilities.json")

            wanted = [str(name).strip() for name in (payload.get("candidates") or []) if str(name).strip()]
            if wanted:
                allowed = set(wanted)
                pack = {**pack, "facilities": [item for item in pack["facilities"] if item["name"] in allowed]}
                if not pack["facilities"]:
                    raise ValueError("候選景點全部不在資料契約內")

            result = plan(pack, prefs)
            self._send_json(200, result.to_dict())
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            self._send_json(400, {"error": f"請求格式不正確：{exc}"})
        except Exception as exc:  # 不讓單次失敗拖垮整個站
            self._send_json(500, {"error": f"求解器執行失敗：{exc}"})

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="InclusiveGo 本地測試伺服器")
    parser.add_argument("--skip-validate", action="store_true", help="跳過資料驗證")
    parser.add_argument("--port", type=int, default=0, help="固定埠號，預設自動選一個可用埠")
    args = parser.parse_args()

    if not args.skip_validate and not run_validation():
        return 1

    handler = partial(InclusiveGoHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"InclusiveGo 網站已啟動：{url}", flush=True)
        print("測試完畢請按 Control-C 停止。", flush=True)
        Timer(0.5, webbrowser.open, args=(url,)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n網站已停止。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())   
