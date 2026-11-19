"""重建 assets/fonts 的 Noto Sans TC 子集字型。

用途：PDF 用內嵌字型，確保任何裝置打開都長一樣（不依賴 Adobe CID 字體或用戶端字型）。

做法：
1. 讀 Google Fonts 的 Noto Sans TC 可變字型（NotoSansTC[wght].ttf）
2. 產生 wght=400 / 700 兩個靜態字重
3. 依專案實際會用到的字元（設施資料、前端字串、PDF 樣板）＋ Big5 一級常用字做子集
4. 改寫 name table，避免兩個字重共用同一 PostScript 名稱

用法：
    python3 scripts/build_fonts.py /path/to/NotoSansTC[wght].ttf

字型授權：Noto Sans TC 為 SIL Open Font License 1.1，可自由嵌入與再散布。
"""

import argparse
import json
import re
import sys
from pathlib import Path

from fontTools.subset import Subsetter, Options
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

EXTRA_PUNCT = set(
    "　·・、。，；：！？「」『』（）《》〈〉…—–～％＋－×÷＝／＼＃＆＊＠｜↑↓→←↗✓✗•─"
)
EXTRA_CODES = list(range(0x2010, 0x2028)) + list(range(0xFF01, 0xFF5F))


def collect_charset() -> set[str]:
    chars = {chr(code) for code in range(32, 127)}
    chars |= EXTRA_PUNCT
    chars |= {chr(code) for code in EXTRA_CODES}

    text_sources = [ROOT / "data" / "facilities.json", ROOT / "index.html", ROOT / "pdfgen.py"]
    for path in text_sources:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # 去掉內嵌的大段 base64，避免把圖片資料當文字
        text = re.sub(r"data:[^\"']+", "", text)
        chars |= {ch for ch in text if ch.strip()}

    # Big5 一級常用字（涵蓋香港常用繁體字）
    for hi in range(0xA4, 0xC7):
        for lo in range(0x40, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("big5")
            except Exception:
                continue
            if "\u4e00" <= ch <= "\u9fff":
                chars.add(ch)
    return chars


def rename(font: TTFont, subfamily: str, ps_name: str) -> None:
    family = "InclusiveGo Sans TC"
    table = font["name"]
    for rec in list(table.names):
        if rec.nameID == 1:
            rec.string = family
        elif rec.nameID == 2:
            rec.string = subfamily
        elif rec.nameID == 3:
            rec.string = f"{ps_name};inclusivego"
        elif rec.nameID == 4:
            rec.string = f"{family} {subfamily}"
        elif rec.nameID == 6:
            rec.string = ps_name
        elif rec.nameID == 16:
            rec.string = family
        elif rec.nameID == 17:
            rec.string = subfamily
    for name_id in (21, 22, 25):  # 可變字型殘留
        table.removeNames(nameID=name_id)


def build(source: Path) -> None:
    charset = collect_charset()
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    base = TTFont(str(source))

    for subfamily, weight, ps_name in [
        ("Regular", 400, "InclusiveGoSansTC-Regular"),
        ("Bold", 700, "InclusiveGoSansTC-Bold"),
    ]:
        font = instantiateVariableFont(base, {"wght": weight}, inplace=False, optimize=True)
        options = Options()
        options.layout_features = []
        options.hinting = False
        options.desubroutinize = True
        subsetter = Subsetter(options=options)
        subsetter.populate(text="".join(sorted(charset)))
        subsetter.subset(font)
        rename(font, subfamily, ps_name)
        out = FONT_DIR / f"{ps_name}.ttf"
        font.save(out)
        print(f"{out.relative_to(ROOT)}  {out.stat().st_size:,} B")


def main() -> int:
    parser = argparse.ArgumentParser(description="重建 PDF 用的 Noto Sans TC 子集")
    parser.add_argument("source", help="NotoSansTC[wght].ttf 的路徑")
    args = parser.parse_args()
    source = Path(args.source)
    if not source.exists():
        print(f"找不到字型：{source}", file=sys.stderr)
        return 1
    build(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
