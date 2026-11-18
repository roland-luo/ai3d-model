"""把 27_parts_preview.py 出的单件图拼成一张带中文标注的验收板。

用法（系统 python3，不需要 Blender）：
    python3 scripts/blender/28_parts_sheet.py \
        --manifest projects/dragon01/parts/parts_manifest.json \
        --cells projects/dragon01/parts/preview/cells \
        --out projects/dragon01/parts/preview/dragon01_parts_sheet.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

BG = (11, 15, 22)
CARD = (18, 24, 36)
LINE = (40, 50, 68)
TEXT = (238, 242, 248)
DIM = (150, 162, 180)
ACCENT = (232, 170, 92)

FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def fit(img, box_w, box_h):
    iw, ih = img.size
    s = min(box_w / iw, box_h / ih)
    return img.resize((int(iw * s), int(ih * s)), Image.LANCZOS)


def crop_content(img, pad=0.06):
    """单件渲染四周是空背景，裁到物体外接框，避免小件在格子里缩成一粒。"""
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((4, 4)))
    diff = ImageChops.difference(rgb, bg).convert("L")
    mask = diff.point(lambda v: 255 if v > 10 else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    px = int((x1 - x0) * pad) + 4
    py = int((y1 - y0) * pad) + 4
    return img.crop((max(0, x0 - px), max(0, y0 - py),
                     min(img.width, x1 + px), min(img.height, y1 + py)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--cells", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="中国龙 · 分件验收板")
    ap.add_argument("--subtitle", default="9 个可独立编辑的部件 · 源网格不覆盖 · 每个单件 GLB 原点归零")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    parts = manifest["parts"]
    colors = {}
    cfg_path = Path(manifest.get("config", ""))
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        colors = {p["id"]: p.get("color", "#888888") for p in cfg.get("parts", [])}
    cells = Path(args.cells)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    cols, rows = 3, 3
    margin, gap = 30, 20
    cell_w, cell_h = 600, 450
    cap_h = 58
    header_h = 132
    footer_h = 52
    width = margin * 2 + cols * cell_w + (cols - 1) * gap
    height = header_h + rows * (cell_h + cap_h) + (rows - 1) * gap + footer_h + margin

    canvas = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(canvas)

    # 顶栏
    d.text((margin, 30), args.title, font=font(48, True), fill=TEXT)
    d.text((margin, 92), args.subtitle, font=font(22), fill=DIM)
    total_tris = sum(p["tris"] for p in parts)
    right = f"{len(parts)} 件  /  约 {round(total_tris / 1000) * 1000:,} 三角面"
    tw = d.textlength(right, font=font(24, True))
    d.text((width - margin - tw, 42), right, font=font(24, True), fill=ACCENT)
    d.line((margin, header_h - 18, width - margin, header_h - 18), fill=LINE, width=2)

    for i, p in enumerate(parts):
        r, c = divmod(i, cols)
        x = margin + c * (cell_w + gap)
        y = header_h + r * (cell_h + cap_h + gap)
        d.rounded_rectangle((x, y, x + cell_w, y + cell_h + cap_h),
                            radius=14, fill=CARD, outline=LINE, width=2)

        img_path = cells / f"{p['id']}.png"
        if img_path.is_file():
            im = Image.open(img_path).convert("RGB")
            im = crop_content(im)
            im = fit(im, cell_w - 16, cell_h - 16)
            canvas.paste(im, (x + (cell_w - im.width) // 2,
                              y + (cell_h - im.height) // 2))

        # 标注条
        cy = y + cell_h + 8
        d.rounded_rectangle((x + 16, cy + 12, x + 28, cy + 40), radius=4,
                            fill=hex_rgb(colors.get(p["id"], "#888888")))
        d.text((x + 38, cy + 10), p.get("label_zh", p["id"]), font=font(25, True), fill=TEXT)
        idw = d.textlength(p["id"], font=font(16))
        d.text((x + 38, cy + 40), p["id"], font=font(16), fill=DIM)
        faces = f"{p['faces']:,} 面"
        fw = d.textlength(faces, font=font(17))
        d.text((x + cell_w - 16 - fw, cy + 24), faces, font=font(17), fill=DIM)

    foot = "切口是开放边：源网格含非流形连接，补洞只能做到尽力而为；要实体打印可把 solidify_mm 设为 1.0–2.0 后重跑。"
    d.text((margin, height - footer_h + 4), foot, font=font(18), fill=DIM)

    canvas.save(out)
    print(f"已写 {out}  ({width}x{height})")


if __name__ == "__main__":
    main()
