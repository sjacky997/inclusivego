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
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
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

COVER_IMAGE = Path(__file__).resolve().parent / "assets" / "cover-night.jpg"
COVER_PAGE_IMAGE = Path(__file__).resolve().parent / "assets" / "pdf-cover.jpg"
COVER_DEEP = colors.HexColor("#041a38")
COVER_MID = colors.HexColor("#062349")
COVER_BLUE = colors.HexColor("#0b3f96")
COVER_LIME = colors.HexColor("#d7ff3f")

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


COVER_CHIP = _style(9, COVER_LIME, leading=13, bold=True)
COVER_TITLE = _style(33, colors.white, leading=40, bold=True)
COVER_TITLE_EM = _style(33, COVER_LIME, leading=40, bold=True)
COVER_SUB = _style(11, colors.HexColor("#dbe7ff"), leading=17)
COVER_LEDE = _style(9.8, colors.HexColor("#cddaee"), leading=17)
COVER_ITEM = _style(9.5, colors.white, leading=15)
COVER_FOOT = _style(8, colors.HexColor("#9db1cb"), leading=13)


def _heading(text):
    return _para(text, H2)


def _draw_cover(canvas, doc):
    """封面底圖：優先用合成好的整頁封面圖（無接縫），否則退回向量漸層。"""
    if COVER_PAGE_IMAGE.exists():
        canvas.drawImage(str(COVER_PAGE_IMAGE), 0, 0, PAGE_W, PAGE_H, mask=None)
        return

    canvas.saveState()
    canvas.linearGradient(
        0,
        PAGE_H,
        PAGE_W,
        0,
        [COVER_BLUE, COVER_MID, COVER_DEEP],
        positions=[0, 0.52, 1],
    )

    if COVER_IMAGE.exists():
        image = ImageReader(str(COVER_IMAGE))
        image_w, image_h = image.getSize()
        region_x = PAGE_W * 0.38
        region_w = PAGE_W - region_x
        scale = max(region_w / image_w, PAGE_H / image_h)
        draw_w, draw_h = image_w * scale, image_h * scale

        canvas.saveState()
        path = canvas.beginPath()
        path.rect(region_x, 0, region_w, PAGE_H)
        canvas.clipPath(path, stroke=0, fill=0)
        canvas.drawImage(
            image,
            region_x + (region_w - draw_w) / 2,
            (PAGE_H - draw_h) / 2,
            draw_w,
            draw_h,
            mask=None,
        )
        # 輕微壓暗，避免插畫比網站版本過亮
        canvas.setFillColor(colors.Color(COVER_MID.red, COVER_MID.green, COVER_MID.blue, alpha=0.18))
        canvas.rect(region_x, 0, region_w, PAGE_H, stroke=0, fill=1)
        canvas.restoreState()

        # 左緣淡出，讓插畫過渡到深藍底（段數夠多才不會出現條紋）
        fade_w = region_w * 0.52
        steps = 180
        for index in range(steps):
            alpha = 0.97 * (1 - index / (steps - 1))
            canvas.setFillColor(colors.Color(COVER_MID.red, COVER_MID.green, COVER_MID.blue, alpha=alpha))
            canvas.rect(region_x + index * fade_w / steps, 0, fade_w / steps + 0.6, PAGE_H, stroke=0, fill=1)

    canvas.restoreState()


def _cover_flowables(doc_data):
    """封面文字：品牌 chip、標題、副標、導語、四項內容、頁腳說明。"""
    meta = doc_data.get("meta") or []
    created = meta[0] if meta else ""
    flow = [
        _para("我的行程指南", COVER_CHIP),
        Spacer(1, 10),
        _para("海濱樂園", COVER_TITLE),
        _para("安心遊", COVER_TITLE_EM),
        Spacer(1, 10),
        _para("出發前準備 ＋ 社交故事", COVER_SUB),
        Spacer(1, 12),
        _para(
            "讓我在出發前知道會看見甚麼、可能感受到甚麼，以及不舒服的時候可以怎樣做。",
            COVER_LEDE,
        ),
        Spacer(1, 16),
    ]
    for item in ["我的準備清單", "建議安心路線", "景點感官提示", "簡短社交故事"]:
        flow.append(_para(f"・{item}", COVER_ITEM))
    flow.append(Spacer(1, 22))
    if created:
        flow.append(_para(created, COVER_FOOT))
    flow.append(_para("插圖為示意，不代表實際園區位置", COVER_FOOT))
    return flow


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
    # 封面不編頁，內頁由第 1 頁起算
    canvas.drawRightString(PAGE_W - MARGIN, MARGIN - 4 * mm, f"第 {max(1, doc.page - 1)} 頁")
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
    cover_frame = Frame(
        MARGIN + 4,
        PAGE_H * 0.16,
        PAGE_W * 0.47,
        PAGE_H * 0.68,
        id="cover-text",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], onPage=_draw_cover),
            PageTemplate(id="main", frames=[frame], onPage=_footer),
        ]
    )

    story = _cover_flowables(doc_data) + [NextPageTemplate("main"), PageBreak()]
    story += [_cover(doc_data), Spacer(1, 4 * mm)]
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
