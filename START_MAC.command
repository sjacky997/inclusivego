#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 Python 3。請先安裝 Python 3，或參閱 README_先看我.txt。"
  read -r _
  exit 1
fi
python3 serve.py
