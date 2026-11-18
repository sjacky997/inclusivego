"""抽出 index.html 裡最長的一段 inline <script>，交給 node --check 驗語法。

CI 不執行前端，但至少能擋住「改 HTML 改出語法錯誤、頁面整個白掉」這種情況。
只用標準庫，不需要安裝任何 npm 套件。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"


def main() -> int:
    if not INDEX.exists():
        print("找不到 index.html", file=sys.stderr)
        return 2

    node = shutil.which("node")
    if node is None:
        print("找不到 node，無法檢查前端語法。", file=sys.stderr)
        print("安裝方式：brew install node（CI 的 ubuntu runner 已預裝，不需處理）", file=sys.stderr)
        return 2

    html = INDEX.read_text(encoding="utf-8")
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    if not blocks:
        print("找不到 inline <script>", file=sys.stderr)
        return 2

    longest = max(blocks, key=len)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "bundle.js"
        target.write_text(longest, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(target)], capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr.strip(), file=sys.stderr)
            return 1

    print(f"前端語法通過：{len(blocks)} 段 script，檢查最長一段（{len(longest):,} 字元）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
