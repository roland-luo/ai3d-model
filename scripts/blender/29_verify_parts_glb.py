"""重新导入 GLB 做交付验收：组合件 9 个网格、单件原点归零、材质还在。

用法：
    ~/.local/bin/blender -b --python scripts/blender/29_verify_parts_glb.py -- \
        --glb projects/dragon01/parts/glb/dragon01_parts.glb \
        --parts-dir projects/dragon01/parts/glb \
        --expect 9
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = {}
    i = 0
    while i < len(argv):
        key = argv[i].lstrip("-").replace("-", "_")
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            out[key] = argv[i + 1]
            i += 2
        else:
            out[key] = True
            i += 1
    return out


def main():
    args = parse_args()
    glb = Path(args.get("glb", "projects/dragon01/parts/glb/dragon01_parts.glb")).resolve()
    parts_dir = Path(args.get("parts_dir", glb.parent)).resolve()
    expect = int(args.get("expect", 0))
    ok = True

    if not glb.is_file():
        raise SystemExit(f"[×] 找不到组合 GLB：{glb}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    roots = [o for o in bpy.data.objects if o.parent is None]
    total = sum(len(o.data.polygons) for o in meshes)
    print(f"[验] 组合 GLB：{len(meshes)} 个网格，{total:,} 面，根对象 {[o.name for o in roots]}")
    print(f"[验] 部件：{sorted(o.name for o in meshes)}")
    if expect and len(meshes) != expect:
        print(f"[×] 期望 {expect} 个网格，实际 {len(meshes)}")
        ok = False

    singles = sorted(parts_dir.glob("Dragon_*.glb"))
    if not singles:
        print("[!] 没找到 Dragon_*.glb 单件，跳过单件检查")
    for p in singles:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(p))
        objs = [o for o in bpy.data.objects if o.type == "MESH"]
        if len(objs) != 1:
            print(f"[×] {p.name}：期望 1 个网格，实际 {len(objs)}")
            ok = False
            continue
        o = objs[0]
        loc = tuple(round(v, 6) for v in o.location)
        dims = tuple(round(v, 5) for v in o.dimensions)
        mats = [m.name for m in o.data.materials if m]
        zero = all(abs(v) < 1e-5 for v in o.location)
        if not zero:
            print(f"[×] {p.name}：原点没归零 {loc}")
            ok = False
        if not mats:
            print(f"[×] {p.name}：材质丢了")
            ok = False
        print(f"[验] {p.name:26s} 面 {len(o.data.polygons):7,d}  原点 {loc}  尺寸 {dims}  材质 {mats}")

    print("[OK] 验收通过" if ok else "[×] 验收失败，见上面的 [×]")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
