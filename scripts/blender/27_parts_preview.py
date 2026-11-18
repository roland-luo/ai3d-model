"""渲染分件验收图：组装、爆炸、单件联系表。

用法：
    blender -b projects/dragon01/parts/dragon01_parts.blend \
        --python scripts/blender/27_parts_preview.py -- \
        --config projects/dragon01/parts.json --out projects/dragon01/parts/preview

只依赖 Blender 自带 Workbench，几秒出图，不占显卡。
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

BG = (0.035, 0.042, 0.058)


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


def log(msg):
    print(f"[PREVIEW] {msg}", flush=True)


def find_parts():
    return [o for o in bpy.data.objects if o.get("ai3d_part") and o.type == "MESH"]


def world_bounds(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo.x, lo.y, lo.z = min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)
            hi.x, hi.y, hi.z = max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)
    if lo.x > hi.x:
        raise RuntimeError("没有可渲染的分件")
    return lo, hi


def setup_scene(res):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "OBJECT"
    sh.show_shadows = False
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.curvature_ridge_factor = 1.4
    sh.curvature_valley_factor = 1.1
    sh.show_object_outline = True
    sh.background_type = "VIEWPORT"
    sh.background_color = BG
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"

    cam = bpy.data.objects.get("PartsPreview_Camera")
    if cam is None:
        cam_data = bpy.data.cameras.new("PartsPreview_Camera")
        cam = bpy.data.objects.new("PartsPreview_Camera", cam_data)
        scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.clip_end = 20.0
    scene.camera = cam
    return cam


def hide_everything(keep):
    for o in bpy.data.objects:
        if o.type in {"MESH", "LIGHT", "CAMERA", "EMPTY"}:
            o.hide_render = o not in keep
    for o in keep:
        o.hide_render = False


def aim(cam, direction, center, span, aspect, margin=1.14):
    d = direction.normalized()
    cam.location = center - d * 3.0
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()

    # 正交相机下，用包围盒 8 个角在相机平面上的真实投影来定画幅，
    # 否则 3/4 视角会把角、须这类伸出去的部件切掉。
    inv = cam.matrix_world.inverted()
    xs, ys = [], []
    lo = center - span * 0.5
    hi = center + span * 0.5
    for ix in (lo.x, hi.x):
        for iy in (lo.y, hi.y):
            for iz in (lo.z, hi.z):
                p = inv @ Vector((ix, iy, iz))
                xs.append(p.x)
                ys.append(p.y)
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    cam.data.ortho_scale = max(w, h * aspect) * margin

    # 把投影中心挪到画面中心
    cx = (max(xs) + min(xs)) * 0.5
    cy = (max(ys) + min(ys)) * 0.5
    right = cam.matrix_world.to_quaternion() @ Vector((1, 0, 0))
    up = cam.matrix_world.to_quaternion() @ Vector((0, 1, 0))
    cam.location += right * cx + up * cy
    bpy.context.view_layer.update()


def load_config(path):
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {part["id"]: part for part in data.get("parts", [])}


def render_to(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    log(f"写图 {path}")


def main():
    args = parse_args()
    out_dir = Path(args.get("out", "parts/preview")).resolve()
    res = (int(args.get("width", 1920)), int(args.get("height", 1440)))
    cfg = load_config(args.get("config"))
    parts = find_parts()
    if not parts:
        raise SystemExit("[×] 场景里没有 ai3d_part 标记的网格")

    cam = setup_scene(res)
    aspect = res[0] / res[1]
    only = args.get("only")
    if isinstance(only, str):
        only = {s.strip() for s in only.split(",")}
    else:
        only = {"assembled", "exploded", "sheet"}

    # 原始模型、摄影棚和地面不参与渲染
    keep = set(parts) | {bpy.data.objects.get("dragon01_Parts_Root")}
    keep.discard(None)
    hide_everything(keep)

    # ---- 单件图（先跑：在爆炸位移后立即切单件，Workbench 偶尔会出空帧）----
    if "sheet" in only:
        per = Path(args.get("cells", out_dir / "cells"))
        per.mkdir(parents=True, exist_ok=True)
        root = bpy.data.objects.get("dragon01_Parts_Root")
        if root:
            root.hide_render = True
        for o in parts:
            hide_everything({o})
            lo, hi = world_bounds([o])
            center = (lo + hi) * 0.5
            span = hi - lo
            size = max(span.x, span.y, span.z, 1e-4)
            # 每个件用同样的视角；细长件自动放大
            aim(cam, Vector((1.0, -1.5, 0.35)), center,
                Vector((size, size, size)), aspect, margin=1.25)
            render_to(per / f"{o.name}.png")
        hide_everything(keep)
        if root:
            root.hide_render = False

    # ---- 组装图 ----
    if "assembled" in only:
        lo, hi = world_bounds(parts)
        center = (lo + hi) * 0.5
        span = hi - lo
        aim(cam, Vector((0.55, -1.65, 0.30)), center, span, aspect)
        render_to(out_dir / "dragon01_parts_assembled.png")

    # ---- 爆炸图 ----
    if "exploded" in only:
        original = {o.name: o.location.copy() for o in parts}
        for o in parts:
            spec = cfg.get(o.name, {})
            off = spec.get("explode_mm", [0, 0, 0])
            o.location = original[o.name] + Vector(off) / 1000.0
        bpy.context.view_layer.update()
        lo, hi = world_bounds(parts)
        center = (lo + hi) * 0.5
        span = hi - lo
        aim(cam, Vector((0.30, -1.65, 0.14)), center, span, aspect, margin=1.16)
        render_to(out_dir / "dragon01_parts_exploded.png")
        for o in parts:
            o.location = original[o.name]

    log("完成")


if __name__ == "__main__":
    main()
