"""阶段 40（可选）：把 Qwen 生成的 logo / 警告贴纸贴到模型表面。

用法（在跑 stage 之前设置环境变量）：
    AI3D_DECAL_IMAGE=~/ai3d/textures/logo.png
    AI3D_DECAL_POS=0.02,-0.10,0.16      # 世界坐标，一般放在头盔前额
    AI3D_DECAL_SIZE=0.07                # 平面边长（米）
    AI3D_DECAL_ROT=90,0,0               # 欧拉角（度），默认让平面朝向 -Y（相机方向）

原理：建一个细分平面 → Shrinkwrap 贴到模型表面 → 用图片的 alpha 做透明混合。
不保证一次就好看，位置和大小多半要手动微调。
"""

import math
import os
from pathlib import Path

import bpy
from mathutils import Euler, Vector

import _common as C

COLL = "AI3D_DECAL"


def parse_vec(s: str, default):
    try:
        return [float(x) for x in s.split(",")]
    except Exception:
        return default


def run() -> None:
    image_path = os.environ.get("AI3D_DECAL_IMAGE", "")
    if not image_path:
        C.log("[i] 没设 AI3D_DECAL_IMAGE，跳过贴花")
        return
    image_path = Path(os.path.expanduser(image_path)).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)

    obj = C.model_object()
    if obj is None:
        raise RuntimeError("场景里没有 AI3D 网格")

    C.clear_collection(COLL)
    coll = C.ensure_collection(COLL)
    pos = Vector(parse_vec(os.environ.get("AI3D_DECAL_POS", "0,-0.12,0.18"), [0, -0.12, 0.18]))
    size = float(os.environ.get("AI3D_DECAL_SIZE", "0.07"))
    rot = parse_vec(os.environ.get("AI3D_DECAL_ROT", "90,0,0"), [90, 0, 0])

    bpy.ops.mesh.primitive_plane_add(size=size, location=pos)
    decal = bpy.context.active_object
    decal.name = "AI3D_Decal"
    decal.rotation_euler = Euler([math.radians(a) for a in rot], "XYZ")
    C.move_to_collection(decal, coll)

    # 细分后贴合
    with bpy.context.temp_override(active_object=decal, object=decal,
                                   selected_objects=[decal], selected_editable_objects=[decal]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=48)
        bpy.ops.object.mode_set(mode="OBJECT")
    # 先把旋转烘进网格，Shrinkwrap 的 offset 方向才正常
    decal.data.transform(decal.matrix_world)
    decal.matrix_world.identity()

    sw = decal.modifiers.new("AI3D_Shrinkwrap", "SHRINKWRAP")
    sw.target = obj
    sw.wrap_method = "NEAREST_SURFACEPOINT"
    sw.offset = 0.0008
    C.apply_modifier(decal, sw.name)

    solid = decal.modifiers.new("AI3D_Solidify", "SOLIDIFY")
    solid.thickness = 0.0004
    solid.offset = 0.0
    C.apply_modifier(decal, solid.name)

    mat = bpy.data.materials.get("Decal") or bpy.data.materials.new("Decal")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (400, 0)
    bsdf.inputs["Metallic"].default_value = 0.25
    bsdf.inputs["Roughness"].default_value = 0.45
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (0, 0)
    tex.image = bpy.data.images.load(str(image_path), check_existing=True)
    tex.interpolation = "Cubic"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.location = (550, -150)
    trans = nt.nodes.new("ShaderNodeBsdfTransparent")
    trans.location = (350, -200)
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(trans.outputs["BSDF"], mix.inputs[1])
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    decal.data.materials.append(mat)

    C.log(f"[OK] 贴花 {image_path.name} @ {tuple(round(v, 3) for v in pos)}，边长 {size}m")
