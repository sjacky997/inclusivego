"""WSGI 入口：同時服務靜態檔案與 POST /api/plan。

供 PythonAnywhere 等只接受 WSGI 的免費主機使用；
不需要 Flask / Django，全部標準庫。
"""

import json
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solver.planner import Preferences, load_facilities, plan  # noqa: E402

_INDEX = "index.html"
_ALLOWED_EXT = {".html", ".json", ".js", ".css", ".svg", ".jpg", ".jpeg", ".png", ".webp", ".ico", ".txt"}


def _json_response(start_response, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    start_response(status, headers)
    return [body]


def _compute(payload):
    prefs = Preferences(
        budget_min=int(payload.get("budget_min") or 240),
        triggers=tuple(payload.get("triggers") or ()),
        handling=payload.get("handling") or "avoid-high",
        rest_interval=int(payload.get("rest_interval") or 0),
        priority=payload.get("priority") or "low-stimulation",
        meal=payload.get("meal") or "none",
        zone_walk=int(payload.get("zone_walk") or 8),
    )
    pack = load_facilities(ROOT / "data" / "facilities.json")
    wanted = [str(n).strip() for n in (payload.get("candidates") or []) if str(n).strip()]
    if wanted:
        allowed = set(wanted)
        pack = {**pack, "facilities": [f for f in pack["facilities"] if f["name"] in allowed]}
        if not pack["facilities"]:
            raise ValueError("候選景點全部不在資料契約內")
    return plan(pack, prefs).to_dict()


def _read_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    if not length:
        return {}
    raw = environ["wsgi.input"].read(length)
    return json.loads(raw.decode("utf-8"))


def _serve_file(start_response, rel):
    target = (ROOT / rel).resolve()
    if ROOT not in target.parents and target != ROOT:
        return _json_response(start_response, "403 Forbidden", {"error": "路徑不合法"})
    if not target.is_file():
        return _json_response(start_response, "404 Not Found", {"error": f"找不到 {rel}"})

    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if target.suffix == ".html":
        ctype = "text/html"
    if target.suffix == ".json":
        ctype = "application/json"
    charset = "utf-8" if ctype.startswith("text/") or ctype.endswith("json") else None
    if charset:
        ctype = f"{ctype}; charset={charset}"

    data = target.read_bytes()
    start_response("200 OK", [("Content-Type", ctype), ("Content-Length", str(len(data))), ("Cache-Control", "public, max-age=60")])
    return [data]


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"

    if path.rstrip("/") == "/api/pdf" and method == "POST":
        try:
            payload_body = _read_body(environ)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json_response(start_response, "400 Bad Request", {"error": "請求格式不正確"})
        try:
            from pdfgen import build_pdf
        except ImportError:
            return _json_response(start_response, "503 Service Unavailable", {"error": "伺服器未安裝 reportlab，無法產生 PDF"})
        try:
            pdf_bytes = build_pdf(payload_body)
        except Exception as exc:
            return _json_response(start_response, "500 Internal Server Error", {"error": f"PDF 產生失敗：{exc}"})
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf_bytes))),
                ("Content-Disposition", 'attachment; filename="InclusiveGo-story.pdf"'),
                ("Cache-Control", "no-store"),
            ],
        )
        return [pdf_bytes]

    if path.rstrip("/") == "/api/plan":
        if method == "OPTIONS":
            start_response("204 No Content", [("Access-Control-Allow-Origin", "*")])
            return [b""]
        if method != "POST":
            return _json_response(start_response, "405 Method Not Allowed", {"error": "請用 POST 呼叫 /api/plan"})
        try:
            return _json_response(start_response, "200 OK", _compute(_read_body(environ)))
        except ValueError as exc:
            return _json_response(start_response, "400 Bad Request", {"error": str(exc)})
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return _json_response(start_response, "400 Bad Request", {"error": f"請求格式不正確：{exc}"})
        except Exception as exc:
            return _json_response(start_response, "500 Internal Server Error", {"error": f"求解器執行失敗：{exc}"})

    if method not in ("GET", "HEAD"):
        return _json_response(start_response, "405 Method Not Allowed", {"error": "只支援 GET"})

    rel = path.lstrip("/") or _INDEX
    if rel.endswith("/"):
        rel += _INDEX
    if Path(rel).suffix.lower() not in _ALLOWED_EXT:
        return _json_response(start_response, "404 Not Found", {"error": f"找不到 {path}"})
    return _serve_file(start_response, rel)
