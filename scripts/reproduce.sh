#!/usr/bin/env bash
# 一鍵重現：資料契約 → 求解器測試 → 固定輸入雜湊 → 穩健度數字 → 前端語法
# 用法：./scripts/reproduce.sh
set -euo pipefail

cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}

echo "== 1/5 資料契約驗證 =="
$PY scripts/validate.py

echo
echo "== 2/5 求解器與 API 測試 =="
$PY -m unittest discover -s tests -t . -v 2>&1 | tail -n 5

echo
echo "== 3/5 固定輸入重現（雜湊比對）=="
$PY scripts/reproduce_check.py

echo
echo "== 4/5 穩健度數字（回歸比對）=="
$PY scripts/sim_check.py

echo
echo "== 5/5 前端 JS 語法 =="
if [ "${SKIP_FRONTEND:-0}" = "1" ]; then
  echo "已依 SKIP_FRONTEND=1 跳過（不算通過，交付前仍須在 CI 或裝了 node 的機器上跑一次）"
else
  $PY scripts/check_frontend.py
fi

echo
if [ "${SKIP_FRONTEND:-0}" = "1" ]; then
  echo "前 4 步通過；第 5 步已跳過，不得視為全部通過。"
else
  echo "全部通過：別人拿到這份儲存庫，跑這條指令就會得到同一組數字。"
fi
