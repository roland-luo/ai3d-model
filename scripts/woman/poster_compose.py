"""Compose the final summer poster: sky + character + typography + grain."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PROJECT = '/home/roland/ai3d/projects/woman01'
RENDERS = f'{PROJECT}/renders'

FONT_SERIF = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
FONT_SERIF_BOLD = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc'
FONT_SANS = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
FONT_DISPLAY = '/usr/share/fonts/truetype/noto/NotoSerifDisplay-Regular.ttf'
SC_INDEX = 2

CREAM = (255, 251, 240, 255)
GOLD = (232, 205, 158, 255)
INK = (22, 63, 96, 255)


def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def tracked(draw, xy, text, fnt, fill, tracking=0.0, anchor_x='center', anchor_y='baseline', shadow=None):
    """Draw text with letter-spacing. Returns the bbox."""
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    if anchor_x == 'center':
        x = xy[0] - total / 2
    elif anchor_x == 'right':
        x = xy[0] - total
    else:
        x = xy[0]
    y = xy[1]
    asc, desc = fnt.getmetrics()
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=fnt, fill=fill, anchor=f'ls')
        x += w + tracking
    return (xy[0] - total / 2 if anchor_x == 'center' else xy[0], y - asc, total, asc + desc)


def add_text(base, s):
    """All type is authored at 1080x1920 and multiplied by s."""
    W, H = base.size
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    kicker_f = font(FONT_SERIF, int(20 * s), SC_INDEX)
    title_f = font(FONT_SERIF, int(104 * s), SC_INDEX)
    sub_f = font(FONT_SERIF, int(25 * s), SC_INDEX)
    foot_f = font(FONT_SANS, int(16 * s), SC_INDEX)
    tag_f = font(FONT_DISPLAY, int(14 * s))

    cx = 540 * s
    # kicker
    tracked(d, (cx, 112 * s), '夏风 · SUMMER 2026', kicker_f, (246, 222, 178, 255),
            tracking=6.0 * s, anchor_x='center', anchor_y='baseline')
    # hairline
    d.rectangle((cx - 32 * s, 132 * s, cx + 32 * s, 133 * s), fill=(232, 205, 158, 165))
    # title
    tracked(d, (cx, 235 * s), '把夏天', title_f, CREAM,
            tracking=6.0 * s, anchor_x='center', anchor_y='baseline')
    tracked(d, (cx, 355 * s), '穿在身上', title_f, CREAM,
            tracking=6.0 * s, anchor_x='center', anchor_y='baseline')
    # subtitle
    tracked(d, (cx, 412 * s), '白裙、长发，和一阵刚刚好的风。', sub_f, (252, 246, 233, 235),
            tracking=2.0 * s, anchor_x='center', anchor_y='baseline')

    # footer, low corners
    tracked(d, (54 * s, 1868 * s), '原创数字角色 · 非真人复刻', foot_f, (19, 61, 94, 205),
            tracking=1.0 * s, anchor_x='left', anchor_y='baseline')
    tracked(d, (1026 * s, 1868 * s), '3 LOOKS · 3 SKINS', tag_f, (29, 78, 112, 210),
            tracking=3.0 * s, anchor_x='right', anchor_y='baseline')

    # soft shadow under the display type (not the small footer)
    alpha = layer.getchannel('A')
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    shadow.paste((10, 34, 58, 76), (0, 0), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(7 * s))
    shadow = Image.fromarray(np.roll(np.asarray(shadow), int(3 * s), axis=0), 'RGBA')
    # keep the shadow mostly above y=430*s (skip footer)
    smask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(smask).rectangle((0, 0, W, int(440 * s)), fill=255)
    shadow.putalpha(Image.fromarray((np.asarray(shadow.getchannel('A'), np.float32) * np.asarray(smask, np.float32) / 255).astype(np.uint8)))
    base.alpha_composite(shadow)
    base.alpha_composite(layer)
    return base


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else 'preview'
    if stage == 'preview':
        sky_path = f'{RENDERS}/poster_sky.png'
        char_path = f'{RENDERS}/poster_char_preview2.png'
        out = f'{RENDERS}/poster_preview.jpg'
        sky = Image.open(sky_path).convert('RGB').resize((1080, 1920), Image.LANCZOS)
    else:
        sky_path = f'{RENDERS}/poster_sky.png'
        char_path = f'{RENDERS}/poster_char_final.png'
        out = (f'{PROJECT}/夏风海报_4K.png' if stage == 'final'
               else f'{PROJECT}/夏风海报_无字版_4K.png')
        sky = Image.open(sky_path).convert('RGB')
    W, H = sky.size
    s = W / 1080.0
    base = sky.convert('RGBA')

    char = Image.open(char_path).convert('RGBA')
    bbox = char.getchannel('A').getbbox()
    char = char.crop(bbox)
    target_h = int(0.68 * H)
    scale = target_h / char.height
    char = char.resize((max(1, int(char.width * scale)), target_h), Image.LANCZOS)

    # faint warm atmospheric rim behind the figure
    rim = char.getchannel('A').filter(ImageFilter.GaussianBlur(max(2, int(7 * s))))
    rim_layer = Image.new('RGBA', char.size, (255, 249, 235, 0))
    rim_layer.putalpha(rim.point(lambda v: int(v * 0.16)))

    cx = W // 2
    bottom = int(0.940 * H)
    x = cx - char.width // 2
    y = bottom - char.height
    base.alpha_composite(rim_layer, (x, y))
    base.alpha_composite(char, (x, y))

    if stage != 'clean':
        base = add_text(base, s)

    # film grain, very light
    arr = np.asarray(base.convert('RGB'), dtype=np.int16)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 2.1 * s, (arr.shape[0], arr.shape[1], 1))
    noise = np.repeat(noise, 3, axis=2)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    out_img = Image.fromarray(arr, 'RGB')
    out_img.save(out, quality=94)
    if stage in ('final', 'clean'):
        out_img.save(f'{RENDERS}/poster_{stage}_flat.png')
        out_img.resize((1080, 1920), Image.LANCZOS).save(
            f'{PROJECT}/夏风海报_{"预览" if stage == "final" else "无字版_预览"}.jpg', quality=93)
    print('WROTE', out, out_img.size)


if __name__ == '__main__':
    main()
