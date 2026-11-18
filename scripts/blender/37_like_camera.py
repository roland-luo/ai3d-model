"""阶段 37：点赞图标的取景微调 —— 把头盔那套 80mm/2m 的构图收紧到图标大小。

环境变量：
  AI3D_PROJECT     项目名（必填）
  AI3D_LIKE_DIST   相机到物体的距离，默认 1.58 m
  AI3D_LIKE_LENS   焦段，默认 85 mm
  AI3D_LIKE_UP     相机相对物体中心的抬高量，默认 0.20 m
  AI3D_LIKE_AZIM   方位角（度），默认 24（正面偏右一点，露出拇指和指节）
  AI3D_LIKE_FSTOP  光圈，默认 4.0
  AI3D_LIKE_EXPOS  曝光补偿，默认 0.0
"""

import math
import os

import bpy
from mathutils import Vector

import _common as C


def run() -> None:
    scene = bpy.context.scene
    obj = C.model_object()
    if obj is None:
        raise RuntimeError("场景里没有 AI3D 网格")

    dist = float(os.environ.get("AI3D_LIKE_DIST", "1.58"))
    lens = float(os.environ.get("AI3D_LIKE_LENS", "85"))
    up = float(os.environ.get("AI3D_LIKE_UP", "0.20"))
    azim = math.radians(float(os.environ.get("AI3D_LIKE_AZIM", "24")))
    fstop = float(os.environ.get("AI3D_LIKE_FSTOP", "4.0"))

    lo, hi = C.mesh_bounds(obj)
    target = Vector((obj.location.x + (lo.x + hi.x) / 2,
                     obj.location.y + (lo.y + hi.y) / 2,
                     obj.location.z + (lo.z + hi.z) / 2))

    cam = scene.camera
    if cam is None:
        raise RuntimeError("场景里没有相机，先跑 studio")

    horiz = dist * math.cos(math.atan2(up, dist))
    cam.location = (target.x + math.sin(azim) * horiz,
                    target.y - math.cos(azim) * horiz,
                    target.z + up)
    cam.data.lens = lens
    cam.data.sensor_width = 36
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = fstop
    C.look_at(cam, target)
    cam.data.dof.focus_distance = (cam.location - target).length

    scene.view_settings.exposure = float(os.environ.get("AI3D_LIKE_EXPOS", "0.0"))

    # 色彩变换：AgX 会把高饱和橘红压成肉粉色，图标类更适合 Khronos PBR Neutral / Standard
    view = os.environ.get("AI3D_LIKE_VIEW", "Khronos PBR Neutral")
    try:
        scene.view_settings.view_transform = view
        C.log(f"[OK] 色彩变换 {view}")
    except TypeError:
        C.log(f"[!] 没有 {view}，保留 {scene.view_settings.view_transform}")
        view = scene.view_settings.view_transform
    if view == "AgX":
        try:
            scene.view_settings.look = "AgX - Medium High Contrast"
        except TypeError:
            pass
    else:
        try:
            scene.view_settings.look = "None"
        except TypeError:
            pass

    # 背景不要抢戏：压暗一点，让主体亮起来
    world = scene.world
    if world is not None and world.use_nodes:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND" and node.inputs["Strength"].default_value > 0.9:
                node.inputs["Strength"].default_value = 0.9

    C.log(f"[OK] 取景：距离 {dist:.2f} m / {lens:.0f} mm / 抬高 {up:.2f} / 方位 {math.degrees(azim):.0f}° "
          f"/ f/{fstop}，目标 {tuple(round(v, 3) for v in target)}")
    C.record_stage("camera_like", {"dist": dist, "lens": lens, "up": up,
                                   "azim": math.degrees(azim), "fstop": fstop})


if __name__ == "__main__":
    run()
    C.save_blend()
