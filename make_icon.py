#!/usr/bin/env python3
"""
產生 AcroPDF 應用程式圖示
輸出：
  resources/icons/acropdf_1024.png   原始 1024×1024 PNG
  resources/icons/acropdf.icns       macOS icon bundle
  resources/icons/acropdf.ico        Windows icon
"""

import os, subprocess, struct, shutil, zlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent / "resources" / "icons"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024

# ── 色盤 ─────────────────────────────────────────────────
BG_TOP    = (26,  60, 110)   # 深藍
BG_BOT    = (14,  36,  74)   # 更深藍
PAGE_W    = "#FFFFFF"
PAGE_SHD  = (0, 0, 0, 60)
FOLD_CLR  = (220, 228, 240)
RED_BAND  = (196, 48,  43)   # Acrobat 紅
RED_LT    = (228, 80,  72)
ACCENT    = (255, 255, 255)
GRAY_LINE = (180, 190, 210)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    S = size

    # ── 背景圓角正方形 ───────────────────────────────────
    r = int(S * 0.18)
    for y in range(S):
        t = y / S
        c = lerp_color(BG_TOP, BG_BOT, t)
        # 逐行漸層（在 mask 裡裁掉）
        d.line([(0, y), (S, y)], fill=(*c, 255))

    # 圓角 mask
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, S-1, S-1], radius=r, fill=255)
    img.putalpha(mask)

    # ── 文件頁面（帶折角）────────────────────────────────
    px = int(S * 0.20)   # page left
    py = int(S * 0.14)   # page top
    pw = int(S * 0.60)   # page width
    ph = int(S * 0.68)   # page height
    fold = int(S * 0.14)  # fold size

    # 陰影
    shadow_offset = int(S * 0.025)
    sd = ImageDraw.Draw(img)
    sd.polygon([
        (px+shadow_offset, py+fold+shadow_offset),
        (px+pw+shadow_offset, py+shadow_offset),  # 錯誤！→ 修正如下
        (px+shadow_offset+fold, py+shadow_offset),
        (px+pw+shadow_offset, py+shadow_offset),
        (px+pw+shadow_offset, py+ph+shadow_offset),
        (px+shadow_offset, py+ph+shadow_offset),
    ], fill=PAGE_SHD)

    # 頁面本體（無折角部分多邊形）
    page_pts = [
        (px,       py+fold),
        (px+fold,  py),
        (px+pw,    py),
        (px+pw,    py+ph),
        (px,       py+ph),
    ]
    d.polygon(page_pts, fill=PAGE_W)

    # 折角三角
    d.polygon([
        (px,      py+fold),
        (px+fold, py),
        (px+fold, py+fold),
    ], fill=FOLD_CLR)
    d.line([(px, py+fold), (px+fold, py+fold), (px+fold, py)],
           fill=(180, 188, 205, 255), width=max(1, S//200))

    # 頁面外框線
    d.polygon(page_pts, outline=(200, 208, 225, 180), width=max(1, S//256))

    # ── 紅色橫幅（Acrobat 風格）──────────────────────────
    bx1 = px + int(pw * 0.0)
    bx2 = px + pw
    by1 = py + int(ph * 0.30)
    by2 = py + int(ph * 0.58)

    # 漸層紅色（用多條線模擬）
    for i in range(by2 - by1):
        t = i / max(1, by2-by1-1)
        c = lerp_color(RED_LT, RED_BAND, t)
        d.line([(bx1, by1+i), (bx2, by1+i)], fill=(*c, 245))

    # 橫幅上下邊框
    d.line([(bx1, by1), (bx2, by1)], fill=(160, 32, 28, 200), width=max(1, S//300))
    d.line([(bx1, by2), (bx2, by2)], fill=(160, 32, 28, 200), width=max(1, S//300))

    # ── 字母 A（白色，粗體）────────────────────────────
    text_y_center = (by1 + by2) // 2
    font_size = int((by2 - by1) * 0.72)

    text = "A"
    tx = px + int(pw * 0.08)

    # 嘗試載入系統字體
    font = None
    for fp in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                pass

    if font is None:
        font = ImageFont.load_default()

    # 量測文字尺寸
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # 垂直置中
    ty = text_y_center - th // 2 - bbox[1]

    # 陰影
    d.text((tx+max(2, S//300), ty+max(2, S//300)), text, font=font,
           fill=(100, 20, 18, 180))
    # 主文字
    d.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # ── 水平文字線條（模擬文件內容）──────────────────
    lx1 = px + int(pw * 0.10)
    lx2 = px + int(pw * 0.88)
    line_w = max(1, S // 220)
    line_gap = int(ph * 0.055)
    line_color = (*GRAY_LINE, 160)

    # 橫幅上方的線
    for i, frac in enumerate([0.10, 0.18]):
        ly = py + int(ph * frac)
        d.line([(lx1, ly), (lx2, ly)], fill=line_color, width=line_w)

    # 最後那條短一點
    ly = py + int(ph * 0.10)
    d.line([(lx1, ly), (lx1 + int((lx2-lx1)*0.55), ly)],
           fill=line_color, width=line_w)

    # 橫幅下方的線
    for frac in [0.68, 0.76, 0.84]:
        ly = py + int(ph * frac)
        end_x = lx2 if frac != 0.84 else lx1 + int((lx2-lx1)*0.65)
        d.line([(lx1, ly), (end_x, ly)], fill=line_color, width=line_w)

    # ── 右下角小標示 "PDF" ────────────────────────────
    label = "PDF"
    lf_size = int(S * 0.072)
    lf = None
    for fp in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]:
        if os.path.exists(fp):
            try:
                lf = ImageFont.truetype(fp, lf_size)
                break
            except Exception:
                pass
    if lf is None:
        lf = ImageFont.load_default()

    lb = d.textbbox((0, 0), label, font=lf)
    lw = lb[2] - lb[0]
    lh = lb[3] - lb[1]
    # 右下角，頁面內
    lrx = px + pw - int(pw * 0.08) - lw
    lry = py + ph - int(ph * 0.06) - lh
    d.text((lrx, lry - lb[1]), label, font=lf,
           fill=(180, 48, 44, 220))

    return img


# ════════════════════════════════════════════════════════════
# 輸出各格式
# ════════════════════════════════════════════════════════════

def save_png(img: Image.Image, path: Path):
    img.save(str(path), "PNG")
    print(f"✅  {path}")


def save_icns(base_png: Path, out: Path):
    """使用 iconutil（macOS 內建）產生 .icns。"""
    if not shutil.which("iconutil"):
        print("⚠️   iconutil 不在 PATH（非 macOS？），跳過 .icns")
        return

    iconset = out.parent / (out.stem + ".iconset")
    iconset.mkdir(exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    base = Image.open(base_png).convert("RGBA")
    for s in sizes:
        resized = base.resize((s, s), Image.LANCZOS)
        resized.save(str(iconset / f"icon_{s}x{s}.png"))
        if s <= 512:
            resized2 = base.resize((s*2, s*2), Image.LANCZOS)
            resized2.save(str(iconset / f"icon_{s}x{s}@2x.png"))

    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                   check=True)
    shutil.rmtree(iconset)
    print(f"✅  {out}")


def save_ico(base_png: Path, out: Path):
    """產生多尺寸 Windows .ico。"""
    base = Image.open(base_png).convert("RGBA")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    imgs[0].save(str(out), format="ICO",
                 sizes=[(s, s) for s in sizes],
                 append_images=imgs[1:])
    print(f"✅  {out}")


if __name__ == "__main__":
    print("🎨  產生 AcroPDF 圖示…")
    img = draw_icon(SIZE)

    png_path  = OUT_DIR / "acropdf_1024.png"
    icns_path = OUT_DIR / "acropdf.icns"
    ico_path  = OUT_DIR / "acropdf.ico"

    save_png(img, png_path)
    save_icns(png_path, icns_path)
    save_ico(png_path, ico_path)

    # 也存一份給 Qt 讀（各平台通用的 PNG）
    for s in [16, 32, 48, 64, 128, 256, 512]:
        p = OUT_DIR / f"acropdf_{s}.png"
        img.resize((s, s), Image.LANCZOS).save(str(p))

    print("\n🎉  完成！輸出至:", OUT_DIR)
