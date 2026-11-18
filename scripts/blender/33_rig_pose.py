"""AI3D 33_rig_pose.py — 给部件骨架做姿态测试，并渲染预览图。

姿态表、头部特写包含哪些件、相机方向都来自 rig_manifest.json
（源头是 rig.json 的 preview 段），脚本不再写死龙的动作。换模型后
只要在 rig.json 里给出骨名和角度即可。

它只负责“摆姿势 + 出图”，不改 rig、不保存 .blend。

用法：
    ~/.local/bin/blender -b projects/dragon01/rig/dragon01_rig.blend \
      --python scripts/blender/33_rig_pose.py -- \
      --out projects/dragon01/rig/preview --res 1400

产物（默认 <rig>/preview/）：
    rig_rest.png        休息姿势，3/4 视角
    rig_pose_3q.png     动作姿势，3/4 视角
    rig_pose_front.png  动作姿势，正面
    rig_pose_side.png   动作姿势，侧面
    rig_pose_head.png   头部特写（配置了 head_parts 才出）
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HOME = Path.home()


def log(msg: str) -> None:
    print(f"[AI3D pose] {msg}", flush=True)


def die(msg: str) -> None:
    raise SystemExit(f"[×] {msg}")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description="AI3D 骨架姿态测试")
    ap.add_argument("--manifest", default=None,
                    help="默认 <rig>/rig_manifest.json")
    ap.add_argument("--out", default=None, help="输出目录，默认 <rig>/preview")
    ap.add_argument("--res", type=int, default=1400, help="单张边长，默认 1400")
    ap.add_argument("--margin", type=float, default=1.30, help="正交相机留白系数")
    ap.add_argument("--only-rest", action="store_true", help="只渲染休息姿势")
    return ap.parse_args(argv)


def rig_dir_from_scene() -> Path | None:
    if not bpy.data.filepath:
        return None
    return Path(bpy.data.filepath).resolve().parent


def load_manifest(path: str | None) -> tuple[dict, Path]:
    if path:
        p = Path(path).expanduser().resolve()
    else:
        base = rig_dir_from_scene()
        if base is None:
            die("当前没有打开 .blend；请用 -b <rig>.blend 或显式传 --manifest")
        p = base / "rig_manifest.json"
    if not p.is_file():
        die(f"找不到 {p}；请先用 32_rig_parts.py 生成骨架")
    try:
        return json.loads(p.read_text(encoding="utf-8")), p
    except json.JSONDecodeError as e:
        die(f"{p} 不是合法 JSON：第 {e.lineno} 行 {e.msg}")


def find_armature(manifest: dict) -> bpy.types.Object:
    name = manifest.get("rig_name")
    if name:
        arm = bpy.data.objects.get(name)
        if arm and arm.type == "ARMATURE":
            return arm
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE" and o.get("ai3d_rig")]
    if not arms:
        arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        die(f"场景里骨架数量是 {len(arms)}，无法确定用哪一套；清单里 rig_name="
            f"{name!r}")
    return arms[0]


def scene_parts(manifest: dict) -> list[bpy.types.Object]:
    names = list(manifest.get("parts", {}).keys())
    if not names:
        names = [o.name for o in bpy.data.objects if o.get("ai3d_part")]
    parts = []
    missing = []
    for n in names:
        o = bpy.data.objects.get(n)
        if o is None or o.type != "MESH":
            missing.append(n)
        else:
            parts.append(o)
    if missing:
        die(f"当前 .blend 缺少部件：{missing}；请先跑 32_rig_parts.py")
    return parts


def prepare_scene(out_dir: Path, res: int) -> bpy.types.Object:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "OBJECT"
    sh.show_shadows = False
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.curvature_ridge_factor = 0.6
    sh.curvature_valley_factor = 0.4
    scene.display.render_aa = "8"
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    # 透明背景，验收板里直接叠到卡片色上，不会出现一圈深浅不同的方块。
    scene.render.film_transparent = True
    scene.world.color = (0.055, 0.065, 0.08)

    for o in bpy.data.objects:
        if o.type in {"LIGHT", "CAMERA"} or o.name.startswith("AI3D_") or o.type == "ARMATURE":
            o.hide_render = True
        elif o.get("ai3d_part"):
            o.hide_render = False

    old_cam = bpy.data.objects.get("RigPoseCam")
    if old_cam:
        bpy.data.objects.remove(old_cam, do_unlink=True)
    cam_data = bpy.data.cameras.new("RigPoseCam")
    cam = bpy.data.objects.new("RigPoseCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.type = "ORTHO"
    cam_data.lens = 50
    out_dir.mkdir(parents=True, exist_ok=True)
    return cam


def evaluated_bounds(parts: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in parts:
        ev = o.evaluated_get(dg)
        for c in ev.bound_box:
            w = ev.matrix_world @ Vector(c)
            lo.x = min(lo.x, w.x)
            lo.y = min(lo.y, w.y)
            lo.z = min(lo.z, w.z)
            hi.x = max(hi.x, w.x)
            hi.y = max(hi.y, w.y)
            hi.z = max(hi.z, w.z)
    return lo, hi


def aim(cam: bpy.types.Object, parts: list[bpy.types.Object],
        direction: tuple[float, float, float], path: Path, margin: float,
        focus: Vector | None = None) -> None:
    lo, hi = evaluated_bounds(parts)
    ctr = (lo + hi) * 0.5 if focus is None else focus
    span = hi - lo
    d = Vector(direction).normalized()
    cam.location = ctr + d * 2.0
    cam.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    cam.data.ortho_scale = max(span.x, span.y, span.z) * margin
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    log(f"已写 {path.name}")


def wrot(arm: bpy.types.Object, bone: str, axis: str, deg: float) -> None:
    """绕世界轴、以骨头当前 head 为圆心旋转，不碰本地轴。"""
    pb = arm.pose.bones.get(bone)
    if pb is None:
        die(f"姿势表里的骨头不存在：{bone}")
    M = pb.matrix.copy()
    h = pb.head.copy()
    R = Matrix.Rotation(math.radians(deg), 4, axis)
    pb.matrix = Matrix.Translation(h) @ R @ Matrix.Translation(-h) @ M
    bpy.context.view_layer.update()


def run(manifest_path: str | None = None, out_dir: str | None = None,
        res: int = 1400, margin: float = 1.30, only_rest: bool = False) -> dict:
    manifest, mpath = load_manifest(manifest_path)
    rig_dir = mpath.parent
    out = Path(out_dir).expanduser().resolve() if out_dir else (rig_dir / "preview")
    preview = manifest.get("preview") or {}
    cam_cfg = preview.get("camera") or {}
    pose = preview.get("pose") or []

    arm = find_armature(manifest)
    parts = scene_parts(manifest)
    cam = prepare_scene(out, res)
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    arm.data.pose_position = "POSE"
    bpy.context.view_layer.update()

    log(f"休息姿势：3/4 视角（{res}px）")
    aim(cam, parts, tuple(cam_cfg.get("rest", [0.55, -1.65, 0.30])),
        out / "rig_rest.png", margin)
    if only_rest:
        log("[OK] 只渲染休息姿势")
        return {"ok": True, "images": [str(out / "rig_rest.png")], "pose": []}

    applied = []
    for item in pose:
        bone, axis, deg = item[0], item[1], float(item[2])
        wrot(arm, bone, axis, deg)
        applied.append(f"{bone} {axis}{deg:+g}°")
    log("动作姿势：" + ("；".join(applied) if applied else "（配置里没有 pose）"))

    aim(cam, parts, tuple(cam_cfg.get("pose_3q", [0.55, -1.65, 0.30])),
        out / "rig_pose_3q.png", margin)
    aim(cam, parts, tuple(cam_cfg.get("pose_front", [0.0, -1.65, 0.15])),
        out / "rig_pose_front.png", margin)
    aim(cam, parts, tuple(cam_cfg.get("pose_side", [-1.65, 0.0, 0.15])),
        out / "rig_pose_side.png", margin)

    images = [str(out / n) for n in
              ("rig_rest.png", "rig_pose_3q.png", "rig_pose_front.png",
               "rig_pose_side.png")]

    head_names = preview.get("head_parts") or []
    head_objs = [bpy.data.objects.get(n) for n in head_names]
    head_objs = [o for o in head_objs if o is not None and o.type == "MESH"]
    if head_objs:
        lo, hi = evaluated_bounds(head_objs)
        hidden = [bpy.data.objects.get(n) for n in (preview.get("head_hide") or [])]
        hidden = [o for o in hidden if o is not None]
        for o in hidden:
            o.hide_render = True
        aim(cam, head_objs, tuple(cam_cfg.get("head", [0.45, -1.55, 0.35])),
            out / "rig_pose_head.png", margin=1.16, focus=(lo + hi) * 0.5)
        for o in hidden:
            o.hide_render = False
        images.append(str(out / "rig_pose_head.png"))
    else:
        log("配置里没有可用的 head_parts，跳过头部特写")

    log("[OK] 姿态测试渲染完成（未保存 .blend，休息姿势仍是默认）")
    return {"ok": True, "images": images, "pose": applied}


def main() -> None:
    args = parse_args()
    run(args.manifest, args.out, args.res, args.margin, args.only_rest)


if __name__ == "__main__":
    main()
