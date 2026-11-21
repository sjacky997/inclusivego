"""產生 PDF 封面底圖 assets/pdf-cover.jpg（A4 比例，深藍漸層＋右側插畫＋左緣淡出）。

只在需要更新封面素材時執行，執行期不依賴 Pillow：
    python3 scripts/build_cover.py

輸出：assets/pdf-cover.jpg（1240 x 1754，150 dpi，A4 比例）
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "cover-night.jpg"
TARGET = ROOT / "assets" / "pdf-cover.jpg"

WIDTH, HEIGHT = 1240, 1754  # A4 @150dpi
NAVY_TOP = (11, 63, 150)      # #0b3f96
NAVY_MID = (6, 35, 73)        # #062349
NAVY_DEEP = (4, 26, 56)       # #041a38
PHOTO_START = 0.38            # 插畫從版面 38% 開始
FADE_RATIO = 0.52             # 插畫左緣淡出佔插畫寬度的比例
DARKEN = 0.18


def gradient_background() -> Image.Image:
    """以對角線方向插值出深藍漸層。"""
    bg = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(bg)
    for y in range(HEIGHT):
        for_x = y / HEIGHT
        # 由左上往右下加深，中段再過渡到最深
        if for_x < 0.52:
            t = for_x / 0.52
            color = tuple(int(NAVY_TOP[i] + (NAVY_MID[i] - NAVY_TOP[i]) * t) for i in range(3))
        else:
            t = (for_x - 0.52) / 0.48
            color = tuple(int(NAVY_MID[i] + (NAVY_DEEP[i] - NAVY_MID[i]) * t) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return bg


def cover_photo() -> Image.Image:
    """把插畫裁成版面右側比例（等比放大後置中裁切）。"""
    photo = Image.open(SOURCE).convert("RGB")
    region_x = int(WIDTH * PHOTO_START)
    region_w = WIDTH - region_x
    scale = max(region_w / photo.width, HEIGHT / photo.height)
    size = (max(1, round(photo.width * scale)), max(1, round(photo.height * scale)))
    resized = photo.resize(size, Image.LANCZOS)
    left = max(0, (resized.width - region_w) // 2)
    top = max(0, (resized.height - HEIGHT) // 2)
    return resized.crop((left, top, left + region_w, top + HEIGHT))


def fade_mask(width: int, height: int) -> Image.Image:
    """左緣 0 → 右側 255 的水平漸層遮罩。"""
    fade_w = int(width * FADE_RATIO)
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    for x in range(fade_w):
        value = int(255 * (x / fade_w) ** 1.35)
        draw.line([(x, 0), (x, height - 1)], fill=value)
    draw.rectangle([fade_w, 0, width, height - 1], fill=255)
    return mask


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"找不到插畫：{SOURCE}")

    canvas = gradient_background()
    photo = cover_photo()
    mask = fade_mask(photo.width, photo.height)

    region_x = int(WIDTH * PHOTO_START)
    canvas.paste(photo, (region_x, 0), mask)

    # 輕微壓暗，讓插畫與深藍底協調
    if DARKEN:
        overlay = Image.new("RGB", (photo.width, HEIGHT), NAVY_MID)
        canvas.paste(Image.blend(canvas.crop((region_x, 0, WIDTH, HEIGHT)), overlay, DARKEN), (region_x, 0))

    canvas.save(TARGET, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"{TARGET.relative_to(ROOT)}  {TARGET.stat().st_size:,} B")


if __name__ == "__main__":
    main()
