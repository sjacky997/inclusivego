"""Serve this static test package locally without third-party dependencies.

啟動前先驗證 data/facilities.json，資料不合格就不開站，避免用錯資料做 demo。

    python3 serve.py                # 先驗證，再開站
    python3 serve.py --skip-validate  # 跳過驗證（僅限緊急示範）
"""

import argparse
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
import webbrowser


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
        print("    pip install -r requirements.txt", flush=True)
    else:
        print("\n資料驗證失敗，已在上面列出錯誤位置。修正後再啟動：", flush=True)
        print("    python3 scripts/validate.py", flush=True)
        print("如確需暫時略過： python3 serve.py --skip-validate", flush=True)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="InclusiveGo 本地測試伺服器")
    parser.add_argument("--skip-validate", action="store_true", help="跳過資料驗證")
    args = parser.parse_args()

    if not args.skip_validate and not run_validation():
        return 1

    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
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
