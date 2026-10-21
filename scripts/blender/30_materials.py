"""阶段 30：程序化材质（金属 / 橡胶 / 可选镜面），含渲染级倒角与边缘磨损。"""

import json
import os
from pathlib import Path

import bpy

import _common as C

RUBBER = os.environ.get("AI3D_RUBBER", "1") == "1"
VISOR = os.environ.get("AI3D_VISOR", "0") == "1"
DRAGON = os.environ.get("AI3D_LOOK", "helmet").lower() == "dragon"


def _mat(name: str) -> tuple[bpy.types.Material, bpy.types.NodeTree]:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return mat, nt


def _new(nt, typ: str, x: int, y: int):
    n = nt.nodes.new(typ)
    n.location = (x, y)
    return n


def _link(nt, a, out: str, b, inp: str) -> None:
    nt.links.new(a.outputs[out], b.inputs[inp])


def make_metal() -> bpy.types.Material:
    mat, nt = _mat("Helmet_Metal")
    out = _new(nt, "ShaderNodeOutputMaterial", 800, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", 480, 0)
    bsdf.inputs["Metallic"].default_value = 0.75
    bsdf.inputs["Base Color"].default_value = (0.045, 0.05, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.36
    bsdf.inputs["Coat Weight"].default_value = 0.15
    bsdf.inputs["Coat Roughness"].default_value = 0.16
    _link(nt, bsdf, "BSDF", out, "Surface")

    # 细颗粒噪声 → 粗糙度变化
    noise = _new(nt, "ShaderNodeTexNoise", -300, 260)
    noise.inputs["Scale"].default_value = 160.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.55
    rough = _new(nt, "ShaderNodeMapRange", -60, 260)
    rough.inputs["From Min"].default_value = 0.0
    rough.inputs["From Max"].default_value = 1.0
    rough.inputs["To Min"].default_value = 0.32
    rough.inputs["To Max"].default_value = 0.46
    _link(nt, noise, "Fac", rough, "Value")
    _link(nt, rough, "Result", bsdf, "Roughness")

    # Pointiness → 边缘磨损发亮
    geo = _new(nt, "ShaderNodeNewGeometry", -300, 0)
    edge = _new(nt, "ShaderNodeValToRGB", -60, 0)
    edge.color_ramp.elements[0].position = 0.51
    edge.color_ramp.elements[0].color = (0, 0, 0, 1)
    edge.color_ramp.elements[1].position = 0.57
    edge.color_ramp.elements[1].color = (1, 1, 1, 1)
    _link(nt, geo, "Pointiness", edge, "Fac")
    wear = _new(nt, "ShaderNodeMixRGB", 220, 0)
    wear.inputs["Color1"].default_value = (0.075, 0.08, 0.09, 1)
    wear.inputs["Color2"].default_value = (0.32, 0.33, 0.35, 1)
    _link(nt, edge, "Color", wear, "Fac")
    _link(nt, wear, "Color", bsdf, "Base Color")

    # 倒角法线 + 微凹凸
    bevel = _new(nt, "ShaderNodeBevel", 0, -260)
    bevel.samples = 8
    bevel.inputs["Radius"].default_value = 0.0012
    bump = _new(nt, "ShaderNodeBump", 260, -260)
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0004
    _link(nt, noise, "Fac", bump, "Height")
    _link(nt, bevel, "Normal", bump, "Normal")
    _link(nt, bump, "Normal", bsdf, "Normal")

    mat.diffuse_color = (0.04, 0.045, 0.05, 1)
    return mat


def make_rubber() -> bpy.types.Material:
    mat, nt = _mat("Helmet_Rubber")
    out = _new(nt, "ShaderNodeOutputMaterial", 700, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", 380, 0)
    bsdf.inputs["Base Color"].default_value = (0.011, 0.012, 0.014, 1)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Coat Weight"].default_value = 0.08
    bsdf.inputs["Coat Roughness"].default_value = 0.4
    _link(nt, bsdf, "BSDF", out, "Surface")

    noise = _new(nt, "ShaderNodeTexNoise", -100, -180)
    noise.inputs["Scale"].default_value = 420.0
    noise.inputs["Detail"].default_value = 6.0
    bump = _new(nt, "ShaderNodeBump", 180, -180)
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.0002
    _link(nt, noise, "Fac", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


def add_front_uvs(obj: bpy.types.Object, tex_dir: Path) -> bool:
    """把模型正面 XZ 投影到概念图，作为颜色和凹凸贴图的 UV。"""
    meta_path = tex_dir / "dragon_tex_meta.json"
    if not meta_path.is_file():
        return False
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    left, top, right, bottom = meta["bbox"]
    iw, ih = meta["image_size"]
    lo, hi = C.mesh_bounds(obj)
    dx = max(hi.x - lo.x, 1e-9)
    dz = max(hi.z - lo.z, 1e-9)
    u0, u1 = left / iw, (right + 1) / iw
    v0, v1 = 1.0 - (bottom + 1) / ih, 1.0 - top / ih

    me = obj.data
    uv = me.uv_layers.get("AI3D_Front") or me.uv_layers.new(name="AI3D_Front")
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            u = u0 + (co.x - lo.x) / dx * (u1 - u0)
            v = v0 + (co.z - lo.z) / dz * (v1 - v0)
            uv.data[li].uv = (u, v)
    me.uv_layers.active = uv
    C.log(f"正面投影 UV 完成：图片 bbox {left},{top}–{right},{bottom}")
    return True


def make_dragon_gold(tex_dir: Path | None = None) -> bpy.types.Material:
    """旧青铜底 + 凸起处磨亮的金铜色。点云式高模的棱边多，Pointiness 正好当磨损遮罩。"""
    mat, nt = _mat("Dragon_Bronze")
    out = _new(nt, "ShaderNodeOutputMaterial", 940, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", 660, 0)
    bsdf.inputs["Metallic"].default_value = 0.85
    bsdf.inputs["Roughness"].default_value = 0.44
    bsdf.inputs["Coat Weight"].default_value = 0.08
    bsdf.inputs["Coat Roughness"].default_value = 0.12
    _link(nt, bsdf, "BSDF", out, "Surface")

    # 凹处暗青铜，凸起的鳞缘与角爪磨成金铜
    geo = _new(nt, "ShaderNodeNewGeometry", -760, 120)
    edge = _new(nt, "ShaderNodeValToRGB", -560, 120)
    edge.color_ramp.elements[0].position = 0.50
    edge.color_ramp.elements[0].color = (0.010, 0.007, 0.004, 1)
    edge.color_ramp.elements[1].position = 0.66
    edge.color_ramp.elements[1].color = (0.72, 0.40, 0.11, 1)
    _link(nt, geo, "Pointiness", edge, "Fac")

    # 大尺度明暗差，避免整件一个均匀金属色
    noise = _new(nt, "ShaderNodeTexNoise", -760, 380)
    noise.inputs["Scale"].default_value = 11.0
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.6
    tone = _new(nt, "ShaderNodeValToRGB", -560, 380)
    tone.color_ramp.elements[0].position = 0.32
    tone.color_ramp.elements[0].color = (0.34, 0.27, 0.20, 1)
    tone.color_ramp.elements[1].position = 0.72
    tone.color_ramp.elements[1].color = (0.92, 0.82, 0.66, 1)
    _link(nt, noise, "Fac", tone, "Fac")
    mix = _new(nt, "ShaderNodeMixRGB", -300, 250)
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.25
    _link(nt, edge, "Color", mix, "Color1")
    _link(nt, tone, "Color", mix, "Color2")
    _link(nt, mix, "Color", bsdf, "Base Color")

    # 正面投影概念图：颜色补回鳞片层次，高度图补回鳞片起伏
    tex_ok = False
    hscale = None
    if tex_dir is not None:
        alb_path = tex_dir / "dragon_albedo.png"
        hgt_path = tex_dir / "dragon_height.png"
        if alb_path.is_file() and hgt_path.is_file():
            uvn = _new(nt, "ShaderNodeUVMap", -980, 620)
            uvn.uv_map = "AI3D_Front"
            img = bpy.data.images.load(str(alb_path), check_existing=True)
            img.reload()
            tex = _new(nt, "ShaderNodeTexImage", -760, 620)
            tex.image = img
            tex.extension = "EXTEND"
            _link(nt, uvn, "UV", tex, "Vector")
            # 概念图的银灰高光偏冷，往金铜色拉回来
            tint = _new(nt, "ShaderNodeMixRGB", -300, 620)
            tint.blend_type = "MULTIPLY"
            tint.inputs["Fac"].default_value = 0.85
            tint.inputs["Color2"].default_value = (1.0, 0.62, 0.32, 1)
            _link(nt, tex, "Color", tint, "Color1")
            texmix = _new(nt, "ShaderNodeMixRGB", 60, 260)
            texmix.blend_type = "MIX"
            texmix.inputs["Fac"].default_value = 0.32
            _link(nt, mix, "Color", texmix, "Color1")
            _link(nt, tint, "Color", texmix, "Color2")
            _link(nt, texmix, "Color", bsdf, "Base Color")

            himg = bpy.data.images.load(str(hgt_path), check_existing=True)
            himg.reload()
            himg.colorspace_settings.name = "Non-Color"
            htex = _new(nt, "ShaderNodeTexImage", -760, 820)
            htex.image = himg
            htex.extension = "EXTEND"
            _link(nt, uvn, "UV", htex, "Vector")
            bw = _new(nt, "ShaderNodeRGBToBW", -520, 820)
            _link(nt, htex, "Color", bw, "Color")
            hscale = _new(nt, "ShaderNodeMath", -300, 820)
            hscale.operation = "MULTIPLY"
            hscale.inputs[1].default_value = 0.8
            _link(nt, bw, "Val", hscale, 0)
            tex_ok = True

    # 凸边更光、凹处更哑
    rough = _new(nt, "ShaderNodeMapRange", -300, -40)
    rough.inputs["From Min"].default_value = 0.40
    rough.inputs["From Max"].default_value = 0.64
    rough.inputs["To Min"].default_value = 0.62
    rough.inputs["To Max"].default_value = 0.30
    _link(nt, geo, "Pointiness", rough, "Value")
    _link(nt, rough, "Result", bsdf, "Roughness")

    # 微凹凸 + 胞状“鳞片”起伏 + 渲染级倒角
    micro = _new(nt, "ShaderNodeTexNoise", -760, -300)
    micro.inputs["Scale"].default_value = 340.0
    micro.inputs["Detail"].default_value = 8.0
    micro.inputs["Roughness"].default_value = 0.55
    texco = _new(nt, "ShaderNodeTexCoord", -980, -480)
    vor = _new(nt, "ShaderNodeTexVoronoi", -760, -480)
    vor.feature = "F1"
    vor.distance = "EUCLIDEAN"
    vor.inputs["Scale"].default_value = 90.0
    vor.inputs["Randomness"].default_value = 0.9
    _link(nt, texco, "Object", vor, "Vector")
    hsum = _new(nt, "ShaderNodeMath", -300, -390)
    hsum.operation = "ADD"
    _link(nt, micro, "Fac", hsum, 0)
    _link(nt, vor, "Distance", hsum, 1)
    bevel = _new(nt, "ShaderNodeBevel", 120, -300)
    bevel.samples = 8
    bevel.inputs["Radius"].default_value = 0.0007
    bump = _new(nt, "ShaderNodeBump", 380, -300)
    bump.inputs["Strength"].default_value = 0.4
    bump.inputs["Distance"].default_value = 0.0007
    _link(nt, hsum, "Value", bump, "Height")
    _link(nt, bevel, "Normal", bump, "Normal")
    _link(nt, bump, "Normal", bsdf, "Normal")

    if tex_ok:
        # 图像高度当主凹凸，程序化噪声只留一点微纹理
        for link in list(bump.inputs["Height"].links):
            nt.links.remove(link)
        micro_w = _new(nt, "ShaderNodeMath", 120, -520)
        micro_w.operation = "MULTIPLY"
        micro_w.inputs[1].default_value = 0.12
        _link(nt, micro, "Fac", micro_w, 0)
        htex_mix = _new(nt, "ShaderNodeMath", 260, -460)
        htex_mix.operation = "ADD"
        _link(nt, hscale, "Value", htex_mix, 0)
        _link(nt, micro_w, "Value", htex_mix, 1)
        _link(nt, htex_mix, "Value", bump, "Height")
        bump.inputs["Strength"].default_value = 0.5
        bump.inputs["Distance"].default_value = 0.0012

    mat.diffuse_color = (0.30, 0.19, 0.08, 1)
    return mat


def make_visor() -> bpy.types.Material:
    mat, nt = _mat("Helmet_Visor")
    out = _new(nt, "ShaderNodeOutputMaterial", 700, 0)
    bsdf = _new(nt, "ShaderNodeBsdfPrincipled", 380, 0)
    bsdf.inputs["Base Color"].default_value = (0.008, 0.018, 0.028, 1)
    bsdf.inputs["Metallic"].default_value = 0.2
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["Coat Weight"].default_value = 0.8
    bsdf.inputs["Coat Roughness"].default_value = 0.03
    bsdf.inputs["Emission Color"].default_value = (0.05, 0.55, 0.85, 1)
    bsdf.inputs["Emission Strength"].default_value = 0.12
    _link(nt, bsdf, "BSDF", out, "Surface")
    return mat


def run() -> None:
    obj = C.model_object()
    if obj is None:
        raise RuntimeError("场景里没有 AI3D 网格")
    me = obj.data
    lo, hi = C.mesh_bounds(obj)
    height = hi.z - lo.z
    zmin = lo.z

    if DRAGON:
        tex_dir = C.project_dir() / "refs"
        uv_ok = False
        try:
            uv_ok = add_front_uvs(obj, tex_dir)
        except Exception as e:
            C.log(f"[!] 正面投影 UV 失败，退回纯程序化材质：{e}")
        me.materials.clear()
        me.materials.append(make_dragon_gold(tex_dir if uv_ok else None))
        for p in me.polygons:
            p.material_index = 0
        me.update()
        C.log(f"[OK] 龙材质完成：{C.mesh_stats(obj)}")
        return

    metal = make_metal()
    me.materials.clear()
    me.materials.append(metal)

    rubber_idx = None
    if RUBBER:
        me.materials.append(make_rubber())
        rubber_idx = len(me.materials) - 1

    visor_idx = None
    if VISOR:
        me.materials.append(make_visor())
        visor_idx = len(me.materials) - 1

    counts = {i: 0 for i in range(len(me.materials))}
    for p in me.polygons:
        idx = 0
        center = p.center
        if rubber_idx is not None and center.z < zmin + height * 0.085:
            idx = rubber_idx
        elif visor_idx is not None:
            n = p.normal
            if n.y < -0.55 and 0.42 * height < (center.z - zmin) < 0.78 * height:
                idx = visor_idx
        p.material_index = idx
        counts[idx] += 1
    me.update()

    C.log(f"材质面数分配：{ {me.materials[i].name: n for i, n in counts.items()} }")
    C.log(f"[OK] 材质完成：{C.mesh_stats(obj)}")
