"""阶段 41：在产品台前沿加一个「86」铭牌（可选，不属于模型本体）。

环境变量：
  AI3D_PROJECT   项目名（必填）
  AI3D_BADGE     文字，默认 86
  AI3D_BADGE_SIZE 字高（米），默认 0.017
"""

import os

import bpy
from mathutils import Vector

import _common as C


def run() -> None:
    scene = bpy.context.scene
    text = os.environ.get("AI3D_BADGE", "86")
    height = float(os.environ.get("AI3D_BADGE_SIZE", "0.017"))

    coll = C.ensure_collection(C.STUDIO_COLLECTION)
    for old in [o for o in coll.objects if o.name.startswith("AI3D_Badge")]:
        C.clear_collection  # noqa: F841  (占位：下面直接删)
        bpy.data.objects.remove(old, do_unlink=True)

    plinth = next((o for o in coll.objects if o.name.startswith("AI3D_Plinth")), None)
    radius = 0.28
    top = 0.035
    if plinth is not None:
        radius = max(plinth.dimensions.x, plinth.dimensions.y) / 2
        top = plinth.dimensions.z

    curve = bpy.data.curves.new("AI3D_BadgeText", type="FONT")
    curve.body = text
    curve.size = height
    curve.extrude = 0.0012
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new("AI3D_Badge", curve)
    coll.objects.link(obj)

    # 贴在产品台前沿的立面上，正面朝 -Y（相机方向）
    obj.rotation_euler = (1.5708, 0.0, 0.0)
    obj.location = Vector((0.0, -radius + 0.0005, top * 0.52))

    mat = bpy.data.materials.get("Like_Badge") or bpy.data.materials.new("Like_Badge")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = (0.62, 0.86, 1.0, 1.0)
    emi.inputs["Strength"].default_value = 3.0
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    curve.materials.append(mat)

    C.log(f"[OK] 铭牌 {text!r}：字号 {height:.3f} m，贴在半径 {radius:.3f} 的台沿")
    C.record_stage("badge", {"text": text, "size": height})


if __name__ == "__main__":
    run()
    C.save_blend()
