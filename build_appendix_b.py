"""生成《附錄 B：假設值敏感度》DOCX（兩頁）。

資料不手抄：直接呼叫求解器重跑三個情境 × 五個 zone_walk，表格數值與程式輸出一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from solver.planner import Preferences, load_facilities, plan  # noqa: E402

VALUES = (4, 6, 8, 10, 12)
SCENARIOS = [
    ("兩小時／避聲音", Preferences(budget_min=120, triggers=("sound",), rest_interval=45)),
    ("半日／避人群", Preferences(budget_min=240, triggers=("crowd",), rest_interval=45)),
    ("全日／不設避開", Preferences(budget_min=420, triggers=(), rest_interval=45, meal="snack")),
]

CN_FONT = "宋体"
CN_HEAD = "黑体"
EN_FONT = "Times New Roman"


def set_run(run, cn=CN_FONT, size=12, bold=False, color=(0, 0, 0)) -> None:
    run.font.name = EN_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(*color)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn)


def body(doc, text: str) -> None:
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.first_line_indent = Pt(24)
    fmt.line_spacing = 1.5
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_run(p.add_run(text))


def heading(doc, text: str) -> None:
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(14)
    fmt.space_after = Pt(6)
    fmt.keep_with_next = True
    fmt.line_spacing = 1.5
    set_run(p.add_run(text), cn=CN_HEAD, size=16, bold=True)
    # 以 Heading 1 記錄大綱層級，但外觀用上面設定的黑色黑體
    p.style = doc.styles["Heading 1"]
    for run in p.runs:
        set_run(run, cn=CN_HEAD, size=16, bold=True)


def caption(doc, text: str) -> None:
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(4)
    fmt.space_after = Pt(4)
    fmt.keep_with_next = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(p.add_run(text), size=10.5)


def note(doc, text: str) -> None:
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(2)
    fmt.space_after = Pt(10)
    fmt.line_spacing = 1.5
    set_run(p.add_run(text), size=10.5)


def shade(cell, hex_fill: str) -> None:
    tc_pr = cell._element.get_or_add_tcPr()
    elm = OxmlElement("w:shd")
    elm.set(qn("w:val"), "clear")
    elm.set(qn("w:color"), "auto")
    elm.set(qn("w:fill"), hex_fill)
    tc_pr.append(elm)


def no_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    elm = OxmlElement("w:cantSplit")
    tr_pr.append(elm)


def repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    elm = OxmlElement("w:tblHeader")
    tr_pr.append(elm)


def cell_text(cell, text: str, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    fmt = p.paragraph_format
    fmt.space_before = Pt(2)
    fmt.space_after = Pt(2)
    fmt.first_line_indent = Pt(0)
    fmt.line_spacing = 1.0
    set_run(p.add_run(text), size=10.5, bold=bold)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def page_field(doc) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._element.addnext(fld)
    set_run(p.add_run(""), size=10.5)


def run_case(data: dict, prefs: Preferences) -> dict:
    result = plan(data, prefs)
    return {"stops": [s.name for s in result.stops], "walk": result.walk_min, "planned": result.planned_min}


def verdict(case: dict, baseline: dict) -> str:
    if case["stops"] == baseline["stops"]:
        return "相同"
    diff = len(case["stops"]) - len(baseline["stops"])
    if diff < 0:
        return f"少 {-diff} 站"
    if diff > 0:
        return f"多 {diff} 站"
    return "換站"


def main() -> int:
    data = load_facilities()
    rows = []
    for label, prefs in SCENARIOS:
        baseline = run_case(data, Preferences(**{**prefs.__dict__, "zone_walk": 8}))
        for value in VALUES:
            case = run_case(data, Preferences(**{**prefs.__dict__, "zone_walk": value}))
            rows.append((label, value, len(case["stops"]), case["walk"], case["planned"], verdict(case, baseline)))

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, side, Cm(2.5))

    normal = doc.styles["Normal"]
    normal.font.name = EN_FONT
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    normal.paragraph_format.line_spacing = 1.5

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(6)
    title.paragraph_format.space_after = Pt(6)
    set_run(title.add_run("附錄 B　假設值敏感度：跨區步行八分鐘"), cn=CN_HEAD, size=18, bold=True)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(18)
    set_run(sub.add_run("InclusiveGo 海濱樂園共融行程求解器｜技術力優化方案附錄｜2026 年 11 月"), cn="楷体", size=12)

    heading(doc, "一、這張表要回答的問題")
    body(doc, "求解器的時間估算含一個未經實測的假設：由一個區域步行到下一個區域需八分鐘。"
              "這個數字用來把四區串成一條路線，但園區的坡度、電梯位置與人流都沒有實測資料，"
              "因此在程式中列為可調參數（預設八分鐘），而不是寫死在邏輯裡。")
    body(doc, "假設值真正的風險不在「不夠準」，而在「估錯了會不會讓路線整個變樣」。若在合理範圍內重跑，"
              "選出的景點與次序都一樣，這個假設就不影響交付；若一改就少站或換站，就必須在文件與導賞說明中交代，"
              "並保留人手調整的空間。本附錄固定其餘所有條件，只改這一個數字，重跑三個真實使用情境。")

    heading(doc, "二、方法")
    body(doc, "（一）固定條件。設施資料（17 站）、感官門檻（avoid-high，五級以上剔除）、休息間隔與用餐設定全部不動，"
              "只把跨區步行設為四、六、八、十、十二分鐘，並以八分鐘為基準。")
    body(doc, "（二）三個情境。兩小時／避聲音（預算 120 分鐘，休息每 45 分鐘）、半日／避人群（240 分鐘，休息每 45 分鐘）、"
              "全日／不設避開（420 分鐘，休息每 45 分鐘，輕食 15 分鐘）。三者分別對應問卷中最常見的三種答案組合。")
    body(doc, "（三）比較口徑。記錄站數、步行分鐘、合計分鐘（停留＋步行＋休息＋用餐），以及站點名單與八分鐘基準的差異。"
              "步行分鐘由每區「走到最深一站」的累計步行時間，加上區與區之間的轉移組成。")
    body(doc, "（四）可重現。於專案根目錄執行 python3 scripts/sensitivity.py，即可得到下表全部數值。")

    heading(doc, "三、結果")
    caption(doc, "表 B.1　跨區步行假設值對照（三個使用情境）")

    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Cm(3.8), Cm(2.2), Cm(1.6), Cm(2.4), Cm(2.4), Cm(3.6)]
    header = ["情境", "跨區步行", "站數", "步行（分鐘）", "合計（分鐘）", "與八分鐘相比"]
    for idx, (text, width) in enumerate(zip(header, widths)):
        cell = table.rows[0].cells[idx]
        cell.width = width
        cell_text(cell, text, bold=True)
        shade(cell, "D9D9D9")
    repeat_header(table.rows[0])
    no_split(table.rows[0])

    for label, value, count, walk, planned, compare in rows:
        row = table.add_row()
        for idx, width in enumerate(widths):
            row.cells[idx].width = width
        cell_text(row.cells[0], label, align=WD_ALIGN_PARAGRAPH.LEFT)
        cell_text(row.cells[1], f"{value} 分鐘")
        cell_text(row.cells[2], str(count))
        cell_text(row.cells[3], f"{walk:.0f}")
        cell_text(row.cells[4], f"{planned:.0f}")
        cell_text(row.cells[5], compare, align=WD_ALIGN_PARAGRAPH.CENTER)
        no_split(row)

    for r in range(1, len(rows), 5):
        table.cell(r, 0).merge(table.cell(r + 4, 0))
        cell_text(table.cell(r, 0), rows[r - 1][0], align=WD_ALIGN_PARAGRAPH.LEFT)

    note(doc, "資料來源：InclusiveGo 求解器 2026 年 11 月實測；情境設定見第二節。")

    body(doc, "三個情境在四至八分鐘之間，選站名單完全一致，只有步行與合計分鐘隨假設上升；"
              "把假設推到十分鐘，半日與全日各少一站（昇空奇遇），全日到十二分鐘再少小紅熊堡壘；"
              "兩小時情境則改以四川奇珍館換成大熊貓之旅，站數維持四站。")

    heading(doc, "四、結論")
    body(doc, "（一）四至八分鐘：三條路線的選站與次序完全不變，步行與合計時間的差異在八分鐘以內。"
              "只要實測結果不超過八分鐘，現有路線不需要因這個假設改動。")
    body(doc, "（二）十分鐘以上：時長開始吃掉站點。全日行程由十五站降至十四站，十二分鐘時降至十三站。"
              "若實測超過十分鐘，應把全日預算提高到約四百八十分鐘，或改用「少步行」優先級重算，而不是硬套現有數字。")
    body(doc, "（三）兩小時情境的換站屬等值替代。四川奇珍館與大熊貓之旅在同一預算下互換，站數與合計時間相若，"
              "對使用者體驗影響有限，但導賞說明應提示「路線可能依當日安排微調」。")

    heading(doc, "五、限制與後續")
    body(doc, "（一）每站的步行分鐘由園區底圖的像素座標換算（約一分鐘等於一百二十像素），像素未必等距，"
              "亦未計坡道、電梯與人流等候，屬估算而非測量。")
    body(doc, "（二）八分鐘本身仍是假設。建議實測：由正門售票處慢行至威威天地入口，記三次並取中位數，"
              "回填參數後重跑本表；若實測落在四至八分鐘，上表結論可直接沿用。")
    body(doc, "（三）本次分析同時發現並修正求解器一個缺陷：當後段區域無法在預算內容納時，原版會丟棄整條路線並回傳零站。"
              "修正後允許跳過整區，兩小時情境在十分鐘假設下的結果由零站回復為四站；此修正不改變八分鐘基準下的任何輸出。")

    page_field(doc)
    out = ROOT / "InclusiveGo_附錄B_假設值敏感度.docx"
    doc.save(out)
    print(f"saved: {out} ({out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
