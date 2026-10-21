#!/usr/bin/env python3
"""把与图像边缘连通的近白背景涂成纯白，避免 Hunyuan 把淡阴影/灰底烘成几何。

只处理“和边框连通”的近白像素，所以物体内部的高光不会被误伤。

用法：
    ~/ComfyUI/venv/bin/python ~/ai3d/scripts/whiten_bg.py 输入.png 输出.png [阈值]
阈值默认 240（0–255）。背景偏灰就降低，比如 232；怕吃掉物体就升高，比如 248。
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image

THRESHOLD = 240


def whiten(src: Path, dst: Path, threshold: int) -> tuple[int, int]:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    px = im.load()

    near = [[min(px[x, y]) >= threshold for x in range(w)] for y in range(h)]
    seen = [[False] * w for _ in range(h)]
    q: deque[tuple[int, int]] = deque()

    for x in range(w):
        q.append((x, 0))
        q.append((x, h - 1))
    for y in range(h):
        q.append((0, y))
        q.append((w - 1, y))

    changed = 0
    while q:
        x, y = q.popleft()
        if seen[y][x]:
            continue
        seen[y][x] = True
        if not near[y][x]:
            continue
        px[x, y] = (255, 255, 255)
        changed += 1
        if x > 0:
            q.append((x - 1, y))
        if x < w - 1:
            q.append((x + 1, y))
        if y > 0:
            q.append((x, y - 1))
        if y < h - 1:
            q.append((x, y + 1))

    im.save(dst)
    return changed, w * h


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src = Path(sys.argv[1]).expanduser().resolve()
    dst = Path(sys.argv[2]).expanduser().resolve()
    threshold = int(sys.argv[3]) if len(sys.argv) > 3 else THRESHOLD
    if not src.is_file():
        sys.exit(f"[×] 找不到输入图：{src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    changed, total = whiten(src, dst, threshold)
    print(f"[OK] 背景涂白 {changed}/{total} 像素（{changed / total:.1%}）→ {dst}")


if __name__ == "__main__":
    main()
