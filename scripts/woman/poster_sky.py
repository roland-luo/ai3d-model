"""Generate a painterly summer-sky background for the woman01 poster.

Procedural (numpy + PIL): sky gradient, corner sun bloom, volumetric
cumulus clouds built from a warped height field, and a faint low haze.
Output: 2160x3840 RGB PNG.
"""
import numpy as np
from PIL import Image, ImageFilter

W, H = 2160, 3840
SUN = (1.035, 0.012)  # mostly outside the top-right corner: a sun bloom, not a disc


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def gradient_sky():
    stops = [
        (0.00, (16, 56, 103)),
        (0.15, (23, 79, 139)),
        (0.34, (42, 111, 171)),
        (0.55, (72, 143, 194)),
        (0.73, (111, 173, 211)),
        (0.87, (152, 199, 226)),
        (1.00, (190, 221, 237)),
    ]
    ys = np.linspace(0.0, 1.0, H, dtype=np.float32)
    rgb = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        vals = np.array([s[1][ch] for s in stops], dtype=np.float32)
        pos = np.array([s[0] for s in stops], dtype=np.float32)
        rgb[:, :, ch] = np.interp(ys, pos, vals).astype(np.float32)[:, None]
    xs = np.linspace(0.0, 1.0, W, dtype=np.float32)
    lateral = 1.0 - 0.05 * np.exp(-(xs / 0.32) ** 2)
    rgb *= lateral[None, :, None]
    return rgb


def add_sun(img):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = (xx / W - SUN[0]) * W
    dy = (yy / H - SUN[1]) * H
    r = np.sqrt(dx * dx + dy * dy)
    # a soft, searing corner bloom with a small warm heart
    bloom = 0.74 * np.exp(-(r / 980.0) ** 1.35) + 0.24 * np.exp(-(r / 2050.0) ** 2)
    heart = np.exp(-(r / 230.0) ** 2) * 0.62
    warm = np.array([1.0, 0.94, 0.82], dtype=np.float32)
    pale = np.array([0.93, 0.97, 1.0], dtype=np.float32)
    tint = warm * (heart / 0.75)[..., None] + pale * (1.0 - (heart / 0.75)[..., None])
    src = tint * np.clip(bloom + heart, 0, 1.5)[..., None] * 255.0
    img[:] = 255.0 - (255.0 - img) * np.clip(255.0 - src, 0, 255.0) / 255.0

    # subtle separation shading behind the figure so the white dress reads
    dx2 = (xx / W - 0.5) * W
    dy2 = (yy / H - 0.58) * H
    sep = np.exp(-((dx2 / 600.0) ** 2 + (dy2 / 1300.0) ** 2))
    img *= (1.0 - 0.075 * sep[..., None])
    return img


def value_noise(w, h, cells_x, cells_y, seed):
    g = np.random.default_rng(seed).random((cells_y + 2, cells_x + 2)).astype(np.float32)
    im = Image.fromarray((g * 255).astype(np.uint8), 'L').resize((w, h), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) / 255.0


def fbm(w, h, base_x, base_y, octaves, seed, gain=0.55):
    total = np.zeros((h, w), dtype=np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        cx = max(2, int(base_x * (2 ** o)))
        cy = max(2, int(base_y * (2 ** o)))
        total += amp * value_noise(w, h, cx, cy, seed + o * 17)
        norm += amp
        amp *= gain
    return total / norm


def make_puffs(seed, big=1.0):
    """A cumulus mound: two basal rows and a few smaller caps."""
    r = np.random.default_rng(seed)
    puffs = []
    base_n = 5
    for i in range(base_n):
        px = -0.66 + i * (1.32 / (base_n - 1)) + r.uniform(-0.05, 0.05)
        py = 0.46 + r.uniform(-0.05, 0.08)
        pr = (0.34 + r.uniform(-0.06, 0.07)) * big
        puffs.append((px, py, pr, 1.0))
    for i in range(4):
        px = -0.45 + i * 0.30 + r.uniform(-0.06, 0.06)
        py = 0.12 + r.uniform(-0.08, 0.06)
        pr = (0.29 + r.uniform(-0.05, 0.07)) * big
        puffs.append((px, py, pr, 0.96))
    for i in range(3):
        px = -0.28 + i * 0.28 + r.uniform(-0.05, 0.05)
        py = -0.20 + r.uniform(-0.06, 0.05)
        pr = (0.21 + r.uniform(-0.04, 0.06)) * big
        puffs.append((px, py, pr, 0.9))
    puffs.append((0.10 + r.uniform(-0.08, 0.08), -0.44, 0.19 * big, 0.82))
    # small fillers so the flat base does not split into separate lobes
    for px in (-0.30, 0.02, 0.34):
        puffs.append((px + r.uniform(-0.04, 0.04), 0.50 + r.uniform(-0.02, 0.03),
                      0.26 * big, 0.72))
    return puffs


def add_cloud(img, c):
    cx, cy, rx, ry = c['cx'], c['cy'], c['rx'], c['ry']
    strength = c['strength']
    pad = 1.45
    x0 = max(0, int((cx - pad * rx) * W))
    x1 = min(W, int((cx + pad * rx) * W))
    y0 = max(0, int((cy - pad * ry) * H))
    y1 = min(H, int((cy + pad * ry) * H))
    rw, rh = x1 - x0, y1 - y0
    if rw < 8 or rh < 8:
        return

    xx = (np.arange(rw, dtype=np.float32) + x0) / W
    yy = (np.arange(rh, dtype=np.float32) + y0) / H
    dx = (xx[None, :] - cx) / rx
    dy = (yy[:, None] - cy) / ry
    envelope = np.exp(-(dx ** 8 + dy ** 8))

    warp_x = fbm(rw, rh, 4, 3, 4, c['seed'] + 301) - 0.5
    warp_y = fbm(rw, rh, 3, 2, 4, c['seed'] + 907) - 0.5
    wdx = dx + warp_x * 0.34
    wdy = dy + warp_y * 0.20

    # union of soft domes -> both silhouette and a height field for shading
    height = np.zeros((rh, rw), dtype=np.float32)
    for px, py, pr, ph in c['puffs']:
        d2 = ((wdx - px) / pr) ** 2 + ((wdy - py) / (pr * 0.76)) ** 2
        dome = np.sqrt(np.clip(1.0 - d2, 0.0, 1.0)) * ph
        np.maximum(height, dome, out=height)

    detail = fbm(rw, rh, 10, 8, 4, c['seed'] + 41)
    grain = fbm(rw, rh, 26, 20, 3, c['seed'] + 77)
    height *= 0.90 + 0.20 * (detail - 0.5)
    height = np.clip(height, 0, 1)

    alpha = smoothstep(0.05, 0.36, height)
    alpha *= smoothstep(1.04, 0.76, wdy)  # soft flat base
    alpha *= envelope * strength

    aimg = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8), 'L')
    aimg = aimg.filter(ImageFilter.GaussianBlur(2.6))
    alpha = np.asarray(aimg, dtype=np.float32) / 255.0
    if alpha.max() < 0.004:
        return

    # smooth height for believable normals, then light it from the upper right
    himg = Image.fromarray((np.clip(height, 0, 1) * 255).astype(np.uint8), 'L')
    himg = himg.filter(ImageFilter.GaussianBlur(5))
    hs = np.asarray(himg, dtype=np.float32) / 255.0
    gy, gx = np.gradient(hs)
    scale = 22.0
    nx = -gx * scale
    ny = -gy * scale
    lx, ly, lz = 0.55, -0.72, 0.62
    ln = np.sqrt(lx * lx + ly * ly + lz * lz)
    light = np.clip((nx * lx + ny * ly + lz) / (np.sqrt(nx * nx + ny * ny + 1.0) * ln), 0, 1)

    ly_norm = np.clip((dy[:, 0] + 1.0) * 0.5, 0, 1)
    shade = np.clip(0.58 + 0.50 * light + 0.08 * (1.0 - ly_norm[:, None]), 0, 1)
    top = np.array([1.00, 0.995, 0.975], dtype=np.float32) * 255.0
    under = np.array([0.80, 0.86, 0.935], dtype=np.float32) * 255.0
    col = under[None, None, :] + (top - under)[None, None, :] * shade[..., None]
    col *= (0.972 + 0.055 * grain)[..., None]
    # warm kiss from the corner sun
    sun_w = np.exp(-(((cx - SUN[0]) * 1.1) ** 2 + ((cy - SUN[1]) * 0.9) ** 2))
    col += (255.0 * 0.13 * sun_w) * np.array([1.0, 0.90, 0.76], dtype=np.float32)[None, None, :]
    # crisp lit rim
    rim = np.clip((light - 0.64) * 2.6, 0, 1) * np.clip(alpha * 2.0, 0, 1)
    col += rim[..., None] * np.array([26.0, 23.0, 15.0], dtype=np.float32)

    # a soft atmospheric shadow under the cloud, then a luminous halo, then body
    region = img[y0:y1, x0:x1]
    sh = np.asarray(aimg.filter(ImageFilter.GaussianBlur(22)), dtype=np.float32) / 255.0
    sh = np.roll(sh, 12, axis=0) * 0.10
    region[:] = region * (1.0 - sh[..., None]) + np.array([112, 146, 178], dtype=np.float32)[None, None, :] * sh[..., None]
    halo_a = np.asarray(aimg.filter(ImageFilter.GaussianBlur(34)), dtype=np.float32) / 255.0
    ha = (halo_a * 0.20 * strength)[..., None]
    region[:] = region * (1.0 - ha) + 255.0 * ha
    a3 = alpha[..., None]
    region[:] = region * (1.0 - a3) + col * a3


def add_haze(img):
    yy = np.linspace(0, 1, H, dtype=np.float32)
    band = np.exp(-((yy - 0.88) / 0.10) ** 2) * 0.12
    img[:] = img * (1.0 - band[:, None, None]) + np.array([246, 236, 221], dtype=np.float32)[None, None, :] * band[:, None, None]

    w, h = W // 2, H // 2
    xx2 = np.linspace(0, 1, w, dtype=np.float32)
    yy2 = np.linspace(0, 1, h, dtype=np.float32)
    streaks = np.zeros((h, w), dtype=np.float32)
    for cx, cy, sx, sy, amp, seed in [
        (0.20, 0.215, 0.30, 0.020, 0.50, 5),
        (0.76, 0.285, 0.33, 0.016, 0.34, 9),
        (0.34, 0.455, 0.24, 0.014, 0.26, 13),
    ]:
        x = (xx2[None, :] - cx) / sx
        y = (yy2[:, None] - cy) / sy
        env = np.exp(-(x ** 4 + y ** 2))
        n = fbm(w, h, 10, 3, 4, seed)
        streaks += amp * env * smoothstep(0.44, 0.80, n)
    simg = Image.fromarray((np.clip(streaks, 0, 1) * 255).astype(np.uint8), 'L')
    simg = simg.filter(ImageFilter.GaussianBlur(7)).resize((W, H), Image.BICUBIC)
    st = (np.asarray(simg, dtype=np.float32) / 255.0 * 0.18)[..., None]
    img[:] = img * (1.0 - st) + np.array([251, 250, 246], dtype=np.float32)[None, None, :] * st


def main():
    img = gradient_sky()
    add_sun(img)
    clusters = [
        # far, small wisps
        dict(cx=0.08, cy=0.20, rx=0.21, ry=0.055, strength=0.30, seed=11,
             puffs=make_puffs(111, 0.8)),
        # big left bank
        dict(cx=-0.06, cy=0.665, rx=0.27, ry=0.185, strength=0.95, seed=23,
             puffs=make_puffs(231, 1.08)),
        # right bank beside the raised hand
        dict(cx=1.045, cy=0.435, rx=0.255, ry=0.195, strength=0.98, seed=51,
             puffs=make_puffs(511, 1.12)),
        # low corners, behind the feet, quieter
        dict(cx=0.00, cy=0.965, rx=0.30, ry=0.165, strength=0.72, seed=37,
             puffs=make_puffs(371, 1.0)),
        dict(cx=0.985, cy=0.875, rx=0.26, ry=0.150, strength=0.62, seed=67,
             puffs=make_puffs(671, 0.95)),
    ]
    for c in clusters:
        add_cloud(img, c)
    add_haze(img)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xx / W - 0.5) * 2
    ny = (yy / H - 0.5) * 2
    vig = 1.0 - 0.045 * np.clip((nx ** 2 + ny ** 2) * 0.55, 0, 1)
    img *= vig[..., None]

    out = np.clip(img, 0, 255).astype(np.uint8)
    Image.fromarray(out, 'RGB').save('/home/roland/ai3d/projects/woman01/renders/poster_sky.png')
    Image.fromarray(out, 'RGB').resize((1080, 1920), Image.LANCZOS).save('/home/roland/ai3d/projects/woman01/renders/poster_sky_preview.jpg', quality=92)
    print('WROTE poster_sky.png')


if __name__ == '__main__':
    main()
