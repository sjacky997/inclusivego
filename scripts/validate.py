#!/usr/bin/env python3
"""驗證 InclusiveGo 場地內容包。

用法：
    python3 scripts/validate.py
    python3 scripts/validate.py --data data/facilities.json --schema schema/facilities.schema.json
    python3 scripts/validate.py --json

退出碼：0 通過；1 驗證失敗；2 檔案或環境錯誤。

JSON Schema 無法表達的規則（本腳本補上）：
    E001  id 全檔唯一
    E002  name 全檔唯一
    E003  duration.min <= duration.max
    E004  point.map_ref 必須等於內容包頂層 map_ref
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def fatal(message: str, code: int = 2) -> None:
    print(f"[FATAL] {message}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fatal(f"找不到檔案：{path}")
    except OSError as exc:
        fatal(f"無法讀取 {path}：{exc}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        fatal(f"JSON 語法錯誤 {path} 第 {exc.lineno} 行第 {exc.colno} 欄：{exc.msg}")


def check_schema(data: dict, schema: dict) -> list[dict]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fatal("缺少 jsonschema，請先執行 pip install -r requirements.txt")

    validator = Draft202012Validator(schema)
    problems = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in err.path) or "(根層)"
        problems.append({"code": "E000", "path": location, "message": err.message})
    return problems


def check_business_rules(data: dict) -> list[dict]:
    problems: list[dict] = []
    facilities = data.get("facilities") or []
    top_map_ref = data.get("map_ref")

    ids = Counter(item.get("id") for item in facilities)
    for value, count in ids.items():
        if value is not None and count > 1:
            problems.append({
                "code": "E001",
                "path": "facilities",
                "message": f"id 重複 {count} 次：{value}",
            })

    names = Counter(item.get("name") for item in facilities)
    for value, count in names.items():
        if value is not None and count > 1:
            problems.append({
                "code": "E002",
                "path": "facilities",
                "message": f"name 重複 {count} 次：{value}",
            })

    for index, item in enumerate(facilities):
        duration = item.get("duration") or {}
        low, high = duration.get("min"), duration.get("max")
        if isinstance(low, int) and isinstance(high, int) and low > high:
            problems.append({
                "code": "E003",
                "path": f"facilities/{index}/duration",
                "message": f"{item.get('name')}：min {low} 大於 max {high}",
            })

        point = item.get("point") or {}
        if point.get("map_ref") != top_map_ref:
            problems.append({
                "code": "E004",
                "path": f"facilities/{index}/point",
                "message": f"{item.get('name')} 的 map_ref「{point.get('map_ref')}」與頂層「{top_map_ref}」不一致",
            })

    return problems


def collect_warnings(data: dict) -> list[str]:
    facilities = data.get("facilities") or []
    warnings = []

    unknown = sum(1 for item in facilities
                  if (item.get("access") or {}).get("step_free") is None)
    if unknown:
        warnings.append(f"access 未核實：{unknown}/{len(facilities)} 筆（可上線，但介面須顯示「未確認」）")

    levels = {level for item in facilities for level in (item.get("sensory") or {}).values()}
    if levels and max(levels) < 4:
        warnings.append(f"感官值目前只用 {sorted(levels)}，未出現 4-5，建議每次改動後確認是否漏填高刺激")

    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="驗證 InclusiveGo 場地內容包")
    parser.add_argument("--data", default="data/facilities.json", help="資料檔路徑")
    parser.add_argument("--schema", default="schema/facilities.schema.json", help="schema 路徑")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出結果（供 CI 解析）")
    args = parser.parse_args(argv)

    data = load_json(Path(args.data))
    schema = load_json(Path(args.schema))

    problems = check_schema(data, schema) + check_business_rules(data)
    warnings = collect_warnings(data)
    facilities = data.get("facilities") or []
    zones = Counter(item.get("zone") for item in facilities)
    total_min = sum((item.get("duration") or {}).get("min", 0) for item in facilities)
    total_max = sum((item.get("duration") or {}).get("max", 0) for item in facilities)

    if args.json:
        print(json.dumps({
            "ok": not problems,
            "count": len(facilities),
            "errors": problems,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"資料檔：{args.data}")
        print(f"筆數：{len(facilities)}　區域：{'　'.join(f'{k} {v}' for k, v in zones.items())}")
        print(f"全部走完：{total_min}-{total_max} 分鐘")
        for problem in problems:
            print(f"[ERROR {problem['code']}] {problem['path']}：{problem['message']}")
        for warning in warnings:
            print(f"[WARN] {warning}")
        print(f"結果：{len(problems)} 個錯誤，{len(warnings)} 個警告")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
