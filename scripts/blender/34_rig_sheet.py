"""把 33_rig_pose.py 出的预览图拼成一张带中文标注的绑定验收板。

标题、副标题、四格文案、页脚都从 rig.json 的 sheet 段读取（经
rig_manifest.json 传递），所以换模型不用改这个脚本。

用法（系统 python3 + Pillow，不需要 Blender）：
    python3 scripts/blender/34_rig_sheet.py \
        --config projects/dragon01/rig.json \
        --manifest projects/dragon01/rig/rig_manifest.json \
        --preview projects/dragon01/rig/preview \
        --out projects/dragon01/rig/preview/dragon01_rig_sheet.png

图片按 cells 里的顺序读取；每格独立裁掉空背景，保证模型在格子里尽量大。
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
CYAN = (94, 200, 220)

FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

DEFAULT_CELLS = [
    ("rig_rest.png", "休息姿势", "骨架默认状态 · 9 件都在原位", "REST"),
    ("rig_pose_3q.png", "动作 · 3/4", "body +8° · head −14° · 前爪 −20°", "POSE"),
    ("rig_pose_front.png", "动作 · 正面", "颈根 / 腿根由 body 渐变权重跟随", "POSE"),
    ("rig_pose_head.png", "头部特写", "龙须 3 骨平滑 · 角跟 head、鬃毛跟 body", "DETAIL"),
]
DEFAULT_FOOTER = [
    "限制：身体仍是单根 body 骨，不能沿脊柱弯曲；龙头 / 龙须是开放薄壳，大幅转动会看到切口内壁。",
    "下一步：身体重拓扑 + 展 UV + 脊柱骨链，再把头颈拆成 neck / head 两段。重拓扑前别直接上动画。",
]


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def fit(img, box_w, box_h):
    iw, ih = img.size
    s = min(box_w / iw, box_h / ih)
    return img.resize((max(1, int(iw * s)), max(1, int(ih * s))), Image.LANCZOS)


def crop_content(img, pad=0.05):
    """优先用 alpha 裁边；旧图没有 alpha 时退回背景差分。"""
    if img.mode == "RGBA":
        bbox = img.getchannel("A").getbbox()
    else:
        rgb = img.convert("RGB")
        bg = Image.new("RGB", rgb.size, rgb.getpixel((4, 4)))
        diff = ImageChops.difference(rgb, bg).convert("L")
        bbox = diff.point(lambda v: 255 if v > 10 else 0).getbbox()
    if not bbox:
        return img.convert("RGBA")
    x0, y0, x1, y1 = bbox
    px = int((x1 - x0) * pad) + 6
    py = int((y1 - y0) * pad) + 6
    return img.crop((max(0, x0 - px), max(0, y0 - py),
                     min(img.width, x1 + px), min(img.height, y1 + py))).convert("RGBA")


def load_json(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        print(f"⚠ 找不到 {p}，用默认文案")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠ {p} 不是合法 JSON：第 {e.lineno} 行 {e.msg}，用默认文案")
        return {}


def counts_label(manifest: dict, preview: Path) -> str | None:
    if not manifest:
        return None
    n_bones = len(manifest.get("bones", []))
    n_meshes = len(manifest.get("parts", {}))
    if not n_bones or not n_meshes:
        return None
    tris = None
    verify = preview.parent / "verify_report.json"
    if verify.is_file():
        try:
            tris = json.loads(verify.read_text(encoding="utf-8")).get("tris")
        except Exception:
            tris = None
    if not tris:
        tris = (manifest.get("counts") or {}).get("triangles")
    text = f"{n_bones} 骨 · {n_meshes} 件"
    if tris:
        text += f" · 约 {tris / 10000:.0f} 万三角面"
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=None, help="rig.json，用来读 sheet 文案")
    ap.add_argument("--manifest", default=None, help="rig_manifest.json，用来算骨/件数")
    ap.add_argument("--title", default=None)
    ap.add_argument("--subtitle", default=None)
    args = ap.parse_args()

    preview = Path(args.preview)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    cfg = load_json(args.config)
    sheet = cfg.get("sheet", {}) if cfg else {}
    manifest = load_json(args.manifest) or {}

    title = args.title or sheet.get("title") or "中国龙 · 部件级骨架 v1"
    subtitle = args.subtitle or sheet.get(
        "subtitle", "9 个网格 · 14 根骨 · 部件级绑定（身体暂不沿脊柱弯曲）")
    cells = sheet.get("cells") or DEFAULT_CELLS
    footer = sheet.get("footer") or DEFAULT_FOOTER
    right = sheet.get("right") or counts_label(manifest, preview)
    if not right:
        right = "14 骨 · 9 件 · 约 25 万三角面"

    cols, rows = 2, 2
    margin, gap = 30, 24
    cell_w, cell_h = 760, 760
    cap_h = 66
    header_h = 138
    footer_h = 92
    width = margin * 2 + cols * cell_w + (cols - 1) * gap
    height = header_h + rows * (cell_h + cap_h + gap) + footer_h + margin
    canvas = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(canvas)

    d.text((margin, 28), title, font=font(46, True), fill=TEXT)
    d.text((margin, 88), subtitle, font=font(21), fill=DIM)
    tw = d.textlength(right, font=font(23, True))
    d.text((width - margin - tw, 40), right, font=font(23, True), fill=ACCENT)
    d.line((margin, header_h - 20, width - margin, header_h - 20), fill=LINE, width=2)

    for i, (fname, cell_title, sub, tag) in enumerate(cells[:cols * rows]):
        r, c = divmod(i, cols)
        x = margin + c * (cell_w + gap)
        y = header_h + r * (cell_h + cap_h + gap)
        d.rounded_rectangle((x, y, x + cell_w, y + cell_h + cap_h),
                            radius=14, fill=CARD, outline=LINE, width=2)

        img_path = preview / fname
        if img_path.is_file():
            im = Image.open(img_path).convert("RGBA")
            im = crop_content(im)
            im = fit(im, cell_w - 20, cell_h - 20)
            canvas.paste(im, (x + (cell_w - im.width) // 2,
                              y + (cell_h - im.height) // 2), im)
        else:
            d.text((x + 24, y + 24), f"缺图：{fname}", font=font(20), fill=ACCENT)

        cy = y + cell_h + 10
        tag_w = d.textlength(tag, font=font(15, True)) + 22
        d.rounded_rectangle((x + 18, cy + 15, x + 18 + tag_w, cy + 43),
                            radius=8, fill=(30, 40, 56), outline=LINE, width=1)
        d.text((x + 29, cy + 19), tag, font=font(15, True), fill=CYAN)
        d.text((x + 30 + tag_w, cy + 9), cell_title, font=font(26, True), fill=TEXT)
        d.text((x + 30 + tag_w, cy + 39), sub, font=font(16), fill=DIM)

    for i, line in enumerate(footer[:2]):
        d.text((margin, height - footer_h + 8 + i * 32), line, font=font(17), fill=DIM)
    d.line((margin, height - footer_h - 10, width - margin, height - footer_h - 10),
           fill=LINE, width=1)

    canvas.save(out)
    print(f"已写 {out}  ({width}x{height})")


if __name__ == "__main__":
    main()
