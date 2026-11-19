"""把前端送來的結構化內容排成 A4 PDF。

只負責排版，不做任何判斷：內容（需要、路線、故事）全部由前端依求解器結果組好再送進來，
所以 PDF 與螢幕上看到的文字必然一致。

中文字體用 reportlab 內建的 STSong-Light（CID 字體），不必隨專案附字型檔。
"""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# 以專案內嵌的 Noto Sans TC 子集為主字體（與網站黑體觀感一致、任何裝置都長一樣）；
# 找不到字型檔時退回 reportlab 內建的 STSong-Light，避免整個 PDF 端點掛掉。
_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONTS = {
    "normal": _FONT_DIR / "InclusiveGoSansTC-Regular.ttf",
    "bold": _FONT_DIR / "InclusiveGoSansTC-Bold.ttf",
}
FONT = "InclusiveGoSansTC"
FONT_BOLD = "InclusiveGoSansTC-Bold"


def _register_fonts():
    try:
        if not all(path.exists() for path in _FONTS.values()):
            raise FileNotFoundError("字型檔不完整")
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont(FONT, str(_FONTS["normal"])))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_FONTS["bold"])))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)
        return FONT, FONT_BOLD
    except Exception:
        if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light", "STSong-Light"


FONT, FONT_BOLD = _register_fonts()

INK = colors.HexColor("#10213a")
BRAND = colors.HexColor("#075ed8")
SOFT = colors.HexColor("#5a6675")
LINE = colors.HexColor("#c8dbf5")
BOX_BG = colors.HexColor("#f5f8fd")
SENSORY_BG = colors.HexColor("#eaf3ff")
PLANB_BG = colors.HexColor("#fff7dc")

PAGE_W, PAGE_H = A4
MARGIN = 14 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _style(size=9.5, color=INK, leading=None, space_before=0, space_after=0, bold=False):
    return ParagraphStyle(
        f"s{size}{color}{'b' if bold else ''}",
        fontName=FONT_BOLD if bold else FONT,
        fontSize=size,
        leading=leading or size * 1.6,
        textColor=color,
        spaceBefore=space_before,
        spaceAfter=space_after,
        alignment=TA_LEFT,
    )


TITLE = _style(19, colors.white, leading=24, space_after=2, bold=True)
SUBTITLE = _style(9.5, colors.white, leading=14, space_after=1)
BRAND_TXT = _style(8.5, colors.white, leading=12, space_after=3)
H2 = _style(12.5, INK, leading=17, space_before=4, space_after=5, bold=True)
BODY = _style(9.5)
SMALL = _style(8.5, SOFT)
LABEL = _style(9, BRAND, leading=13)

def _para(text, style=BODY):
    """把純文字包成 Paragraph，並跳脫 XML 特殊字元。"""
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _box(flowables, bg=None, border=LINE, width=None):
    width = width or CONTENT_W
    inner_w = width - 8 * mm
    inner = Table([[f] for f in flowables], colWidths=[inner_w])
    style = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    inner.setStyle(TableStyle(style))
    outer = Table([[inner]], colWidths=[width])
    outer_style = [
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("BACKGROUND", (0, 0), (-1, -1), bg or colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5 * mm),
    ]
    outer.setStyle(TableStyle(outer_style))
    return outer


def _heading(text):
    return _para(text, H2)


def _cover(doc_data):
    """藍色標題帶：品牌、標題、副標，白字，模仿網站封面區塊。"""
    lines = []
    if doc_data.get("brand"):
        lines.append(_para(doc_data["brand"], BRAND_TXT))
    lines.append(_para(doc_data.get("title", "我的海濱樂園行前故事"), TITLE))
    if doc_data.get("subtitle"):
        lines.append(_para(doc_data["subtitle"], SUBTITLE))
    band = Table([[lines]], colWidths=[CONTENT_W])
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND),
                ("LEFTPADDING", (0, 0), (-1, -1), 8 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 8 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8 * mm),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return band


def _summary_block(data):
    rows = [[_para(label, LABEL), _para(value)] for label, value in data.get("rows", [])]
    inner_w = CONTENT_W - 8 * mm
    grid = Table(rows, colWidths=[inner_w * 0.24, inner_w * 0.76])
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return KeepTogether([_heading(data.get("heading", "我的需要與安排")), _box([grid])])


def _checklist_block(data):
    body = [
        Paragraph(
            escape(str(text)),
            ParagraphStyle("b", parent=BODY, leftIndent=10, bulletIndent=0, bulletText="•", spaceAfter=2),
        )
        for text in data.get("items", [])
    ]
    return KeepTogether([_heading(data.get("heading", "我的出發前準備清單")), _box(body or [_para("（未選擇任何項目）")])])


def _route_block(data):
    rows = []
    for index, item in enumerate(data.get("items", []), start=1):
        cell = [_para(f"{index}. {item.get('title', '')}", BODY)]
        sub = item.get("sub") or ""
        if sub:
            cell.append(_para(sub, SMALL))
        rows.append([cell])
    body = []
    for cell in rows:
        body.extend(cell)
        body.append(Spacer(1, 3))
    return KeepTogether([_heading(data.get("heading", "我的建議路線")), _box(body or [_para("（尚未加入景點）")]) ])


def _story_groups(stories, cap=3):
    """把故事盡量平均分成若干頁，單頁最多 cap 則（4 則 -> 2+2）。"""
    total = len(stories)
    if total == 0:
        return []
    pages = -(-total // cap)  # ceil
    base, extra = divmod(total, pages)
    groups, start = [], 0
    for index in range(pages):
        size = base + (1 if index < extra else 0)
        groups.append(stories[start : start + size])
        start += size
    return groups


def _story(story, tail=None):
    inner_w = CONTENT_W - 8 * mm
    head = _para(f"{story.get('no', '')}. {story.get('title', '')}", _style(12, INK, leading=16))
    parts = [head]
    if story.get("sub"):
        parts.append(_para(story["sub"], SMALL))
    if story.get("sensory"):
        parts.append(Spacer(1, 3))
        parts.append(
            _box([_para(f"感官提示：{story['sensory']}", BODY)], bg=SENSORY_BG, border=SENSORY_BG, width=inner_w)
        )
    if story.get("access"):
        parts.append(_para(f"無障礙資訊：{story['access']}", SMALL))
    two_col = Table(
        [
            [
                [_para("我會經歷甚麼", LABEL), _para(story.get("experience", ""))],
                [_para("我可以準備甚麼", LABEL), _para(story.get("prep", ""))],
            ]
        ],
        colWidths=[inner_w / 2, inner_w / 2],
    )
    two_col.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("BACKGROUND", (0, 0), (-1, -1), BOX_BG),
            ]
        )
    )
    parts.append(Spacer(1, 3))
    parts.append(two_col)
    parts.append(Spacer(1, 3))
    parts.append(
        _box(
            [
                _para(
                    "如果我不想繼續：我可以說「我要休息」、離開、略過這一站，或改到下一個較合適的景點。",
                    BODY,
                )
            ],
            bg=PLANB_BG,
            border=colors.HexColor("#f4ba16"),
            width=inner_w,
        )
        )
    if tail:
        parts.append(Spacer(1, 4 * mm))
        parts.append(tail)
    return KeepTogether([_box(parts)])


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(SOFT)
    canvas.drawString(MARGIN, MARGIN - 4 * mm, "InclusiveGo 共融智遊")
    canvas.drawRightString(PAGE_W - MARGIN, MARGIN - 4 * mm, f"第 {doc.page} 頁")
    canvas.restoreState()


def build_pdf(doc_data: dict) -> bytes:
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 4 * mm,
        title=doc_data.get("title", "InclusiveGo 個人化行前故事"),
        author="InclusiveGo 共融智遊",
    )
    frame = Frame(MARGIN, MARGIN + 4 * mm, CONTENT_W, PAGE_H - 2 * MARGIN - 4 * mm, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_footer)])

    story = [_cover(doc_data), Spacer(1, 4 * mm)]
    for line in doc_data.get("meta", []):
        story.append(_para(line, SMALL))
    story.append(Spacer(1, 5 * mm))

    if doc_data.get("summary"):
        story.append(_summary_block(doc_data["summary"]))
        story.append(Spacer(1, 5 * mm))
    if doc_data.get("checklist"):
        story.append(_checklist_block(doc_data["checklist"]))
        story.append(Spacer(1, 5 * mm))
    if doc_data.get("route"):
        story.append(_route_block(doc_data["route"]))
        story.append(Spacer(1, 5 * mm))

    stories = doc_data.get("stories", [])
    footnote = _para(doc_data["footnote"], SMALL) if doc_data.get("footnote") else None

    # 故事平均分配到各頁（每頁最多 3 則），避免最後一頁只剩一則、大面積留白
    per_page = _story_groups(stories)
    for page_index, group in enumerate(per_page):
        if page_index > 0:
            story.append(PageBreak())
        for offset, item in enumerate(group):
            index = sum(len(g) for g in per_page[:page_index]) + offset
            # 附註跟著最後一則故事同頁，避免落單產生空白頁
            tail = footnote if (footnote is not None and index == len(stories) - 1) else None
            story.append(_story(item, tail=tail))
            if offset < len(group) - 1:
                story.append(Spacer(1, 4 * mm))

    if footnote is not None and not stories:
        story.append(Spacer(1, 3 * mm))
        story.append(footnote)

    doc.build(story)
    return buffer.getvalue()
