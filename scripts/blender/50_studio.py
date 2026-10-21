"""阶段 50：摄影棚 —— 无缝背景、产品台、四灯、85mm 相机、AgX、轻微辉光。"""

import math
import os

import bpy
from mathutils import Vector

import _common as C

DRAGON = os.environ.get("AI3D_LOOK", "helmet").lower() == "dragon"
PEARL = os.environ.get("AI3D_PEARL", "1" if DRAGON else "0") == "1"
PLINTH_H = 0.022 if DRAGON else 0.035
PLINTH_R = float(os.environ.get("AI3D_PLINTH_R", "0.165" if DRAGON else "0.28"))
RING = os.environ.get("AI3D_RING", "1") == "1"


def _studio_obj(obj, coll):
    C.move_to_collection(obj, coll)
    return obj


def make_cyclorama(coll):
    xs = [-7.0 + i * (14.0 / 24) for i in range(25)]
    profile = []
    for y in (-6.0, -4.5, -3.0, -1.5, 0.0, 1.0):
        profile.append((y, 0.0))
    R = 1.5
    for i in range(1, 17):
        t = (math.pi / 2) * (i / 16)
        profile.append((1.0 + R * (1 - math.cos(t)), R * math.sin(t)))
    for z in (R + 2.0, R + 4.0, 8.0):
        profile.append((1.0 + R, z))

    verts = []
    for x in xs:
        for y, z in profile:
            verts.append((x, y, z))
    faces = []
    n = len(profile)
    for i in range(len(xs) - 1):
        for j in range(n - 1):
            a = i * n + j
            b = (i + 1) * n + j
            c = (i + 1) * n + j + 1
            d = i * n + j + 1
            faces.append((a, b, c, d))
    me = bpy.data.meshes.new("AI3D_Cyc")
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new("AI3D_Cyc", me)
    coll.objects.link(obj)
    for p in me.polygons:
        p.use_smooth = True

    mat = bpy.data.materials.get("Studio_Backdrop") or bpy.data.materials.new("Studio_Backdrop")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (350, 120)
    bsdf.inputs["Roughness"].default_value = 0.62
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    tex = nt.nodes.new("ShaderNodeTexCoord")
    tex.location = (-900, 0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-720, 0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-480, 200)
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 1.0
    mid = ramp.color_ramp.elements.new(0.35)
    if DRAGON:
        # 幕布本身几乎不接光，画面只剩背后的红色氛围光
        ramp.color_ramp.elements[0].color = (0.0004, 0.0003, 0.00025, 1)
        ramp.color_ramp.elements[1].color = (0.0018, 0.0011, 0.0008, 1)
        mid.color = (0.0009, 0.0006, 0.0004, 1)
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    else:
        ramp.color_ramp.elements[0].color = (0.006, 0.008, 0.012, 1)
        ramp.color_ramp.elements[1].color = (0.022, 0.028, 0.04, 1)
        mid.color = (0.012, 0.014, 0.02, 1)
    nt.links.new(tex.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    # 背景氛围光：不用面光（会投出方形光斑），在幕布材质里做径向自发光。
    # 圆心对准头盔在画面里的正后方，边缘自然衰减到黑。
    center = nt.nodes.new("ShaderNodeCombineXYZ")
    center.location = (-720, -320)
    center.inputs["X"].default_value = -0.1 if DRAGON else -1.2
    center.inputs["Y"].default_value = 1.02 if DRAGON else 2.2
    center.inputs["Z"].default_value = 0.22 if DRAGON else 0.9
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    dist.location = (-480, -320)
    nt.links.new(tex.outputs["Object"], dist.inputs[0])
    nt.links.new(center.outputs["Vector"], dist.inputs[1])
    norm = nt.nodes.new("ShaderNodeMath")
    norm.operation = "DIVIDE"
    norm.location = (-300, -320)
    norm.inputs[1].default_value = 0.7 if DRAGON else 2.8
    nt.links.new(dist.outputs["Value"], norm.inputs[0])
    glow = nt.nodes.new("ShaderNodeValToRGB")
    glow.location = (-100, -320)
    glow.color_ramp.elements[0].position = 0.0
    glow.color_ramp.elements[0].color = (1, 1, 1, 1)
    glow.color_ramp.elements[1].position = 1.0
    glow.color_ramp.elements[1].color = (0, 0, 0, 1)
    glow_mid = glow.color_ramp.elements.new(0.35)
    glow_mid.color = (0.16, 0.16, 0.16, 1)
    nt.links.new(norm.outputs["Value"], glow.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.location = (120, -320)
    mix.inputs["Fac"].default_value = 1.0
    mix.inputs["Color2"].default_value = (0.40, 0.012, 0.002, 1) if DRAGON else (0.045, 0.115, 0.30, 1)
    nt.links.new(glow.outputs["Color"], mix.inputs["Color1"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.location = (350, -320)
    em.inputs["Strength"].default_value = 1.3 if DRAGON else 1.15
    nt.links.new(mix.outputs["Color"], em.inputs["Color"])
    add = nt.nodes.new("ShaderNodeAddShader")
    add.location = (540, 0)
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    me.materials.append(mat)
    return obj


def make_plinth(coll):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=96, radius=PLINTH_R, depth=PLINTH_H, location=(0, 0, PLINTH_H / 2)
    )
    obj = bpy.context.active_object
    obj.name = "AI3D_Plinth"
    _studio_obj(obj, coll)
    mod = obj.modifiers.new("PlinthBevel", "BEVEL")
    mod.width = 0.0035
    mod.segments = 3

    mat = bpy.data.materials.get("Studio_Plinth") or bpy.data.materials.new("Studio_Plinth")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    if DRAGON:
        # 暗红大漆台座，压住画面底部
        bsdf.inputs["Base Color"].default_value = (0.006, 0.0007, 0.0005, 1)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.85
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
        bsdf.inputs["Coat Weight"].default_value = 0.0
    else:
        bsdf.inputs["Base Color"].default_value = (0.03, 0.033, 0.04, 1)
        bsdf.inputs["Metallic"].default_value = 0.3
        bsdf.inputs["Roughness"].default_value = 0.42
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def make_ring(coll):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=PLINTH_R - 0.008,
        minor_radius=0.0014,
        major_segments=160,
        minor_segments=8,
        location=(0, 0, PLINTH_H + 0.0005),
    )
    obj = bpy.context.active_object
    obj.name = "AI3D_Ring"
    _studio_obj(obj, coll)
    mat = bpy.data.materials.get("Studio_RingGlow") or bpy.data.materials.new("Studio_RingGlow")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    em = nt.nodes.new("ShaderNodeEmission")
    em.location = (0, 0)
    em.inputs["Color"].default_value = (1.0, 0.38, 0.07, 1) if DRAGON else (0.15, 0.75, 1.0, 1)
    em.inputs["Strength"].default_value = 0.7 if DRAGON else 6.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    obj.data.materials.append(mat)
    return obj


def make_pearl(coll, target):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=64, ring_count=32, radius=0.021,
        location=(0.205, -0.02, 0.22),
    )
    obj = bpy.context.active_object
    obj.name = "AI3D_Pearl"
    _studio_obj(obj, coll)
    for p in obj.data.polygons:
        p.use_smooth = True

    mat = bpy.data.materials.get("Studio_Pearl") or bpy.data.materials.new("Studio_Pearl")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    bsdf.inputs["Base Color"].default_value = (0.18, 0.03, 0.004, 1)
    bsdf.inputs["Metallic"].default_value = 0.1
    bsdf.inputs["Roughness"].default_value = 0.4
    bsdf.inputs["Coat Weight"].default_value = 0.6
    bsdf.inputs["Coat Roughness"].default_value = 0.1
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.25, 0.02, 1)
    bsdf.inputs["Emission Strength"].default_value = 0.7
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.append(mat)

    # 珠子自身照亮龙身右缘，让“戏珠”有互动关系
    data = bpy.data.lights.new("AI3D_PearlLight", "AREA")
    data.energy = 1.0
    data.size = 0.06
    data.color = (1.0, 0.55, 0.25)
    light = bpy.data.objects.new("AI3D_PearlLight", data)
    coll.objects.link(light)
    light.location = obj.location
    C.look_at(light, target)
    return obj


def make_light(coll, name, loc, size, energy, color, size_y=None):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    if size_y:
        data.shape = "RECTANGLE"
        data.size = size
        data.size_y = size_y
    else:
        data.size = size
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    obj.location = loc
    return obj


def setup_cycles(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 64
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.02
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 6
    scene.cycles.transmission_bounces = 8
    scene.cycles.transparent_max_bounces = 8
    scene.render.use_persistent_data = True
    try:
        prefs = bpy.context.preferences.addons.get("cycles")
        if prefs:
            cp = prefs.preferences
            for dev_type in ("OPTIX", "CUDA"):
                try:
                    cp.compute_device_type = dev_type
                    break
                except TypeError:
                    continue
            cp.get_devices()
            enabled = 0
            for d in cp.devices:
                use = d.type != "CPU"
                d.use = use
                enabled += int(use)
            C.log(f"Cycles GPU：{cp.compute_device_type}，启用 {enabled} 个设备")
    except Exception as e:
        C.log(f"[!] GPU 设置失败，退回 CPU：{e}")
        scene.cycles.device = "CPU"


def setup_compositor(scene):
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    rl.location = (-400, 0)
    glare = nt.nodes.new("CompositorNodeGlare")
    glare.location = (-150, 0)
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.2
    glare.size = 7
    glare.mix = -0.9
    comp = nt.nodes.new("CompositorNodeComposite")
    comp.location = (150, 0)
    nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
    nt.links.new(glare.outputs["Image"], comp.inputs["Image"])


def run() -> None:
    scene = bpy.context.scene
    obj = C.model_object()
    if obj is None:
        raise RuntimeError("场景里没有 AI3D 网格")

    C.clear_collection(C.STUDIO_COLLECTION)
    coll = C.ensure_collection(C.STUDIO_COLLECTION)

    # 模型放到产品台上：记录抬升量，改台高后重跑也不会漂空
    prev_lift = float(obj.get("ai3d_lift", 0.035 if obj.get("ai3d_lifted") else 0.0))
    obj.location.z += PLINTH_H - prev_lift
    obj["ai3d_lift"] = PLINTH_H
    obj["ai3d_lifted"] = True
    lo, hi = C.mesh_bounds(obj)
    target_z = obj.location.z + (lo.z + hi.z) / 2
    target = Vector((0.0, 0.0, target_z))

    make_cyclorama(coll)
    make_plinth(coll)
    if RING:
        make_ring(coll)
    if PEARL:
        make_pearl(coll, target)

    if DRAGON:
        # 暖金主光 + 金色背轮廓 + 冷蓝侧逆，红金主调里留一点冷色呼吸
        key = make_light(coll, "AI3D_Key", (-0.75, -1.05, 1.05), 1.5, 95,
                         (1.0, 0.92, 0.82))
        fill = make_light(coll, "AI3D_Fill", (1.05, -0.75, 0.55), 1.3, 10,
                          (0.55, 0.68, 0.95))
        rim = make_light(coll, "AI3D_Rim", (0.35, 0.95, 1.05), 0.6, 300,
                         (1.0, 0.55, 0.20), size_y=0.32)
        top = make_light(coll, "AI3D_Top", (0.0, 0.0, 1.3), 0.7, 34,
                         (1.0, 0.95, 0.88), size_y=0.22)
        accent = make_light(coll, "AI3D_Accent", (-0.95, 0.55, 0.42), 0.35, 40,
                            (0.25, 0.55, 1.0))
    else:
        key = make_light(coll, "AI3D_Key", (-0.85, -1.1, 0.95), 1.6, 90,
                         (1.0, 0.96, 0.9))
        fill = make_light(coll, "AI3D_Fill", (1.15, -0.8, 0.55), 1.2, 22,
                          (0.8, 0.9, 1.0))
        rim = make_light(coll, "AI3D_Rim", (0.4, 1.05, 1.0), 0.55, 260,
                         (0.45, 0.75, 1.0), size_y=0.3)
        top = make_light(coll, "AI3D_Top", (0.0, 0.0, 1.35), 0.8, 26,
                         (1.0, 1.0, 1.0), size_y=0.25)
        accent = make_light(coll, "AI3D_Accent", (-1.0, 0.65, 0.4), 0.35, 30,
                            (1.0, 0.42, 0.15))
    for light in (key, fill, rim, top, accent):
        C.look_at(light, target)

    cam_data = bpy.data.cameras.new("AI3D_Camera")
    cam = bpy.data.objects.new("AI3D_Camera", cam_data)
    coll.objects.link(cam)
    cam_data.lens = 80
    cam_data.sensor_width = 36
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 5.6
    if DRAGON:
        cam.location = (0.52, -1.52, target_z + 0.20)
    else:
        cam.location = (0.88, -1.80, target_z + 0.46)
    C.look_at(cam, target)
    cam_data.dof.focus_distance = (cam.location - target).length
    scene.camera = cam

    world = bpy.data.worlds.get("AI3D_World") or bpy.data.worlds.new("AI3D_World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    out.location = (700, 0)

    # 相机直接看到的背景：很暗，保持海报对比
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.location = (200, 160)
    bg.inputs["Color"].default_value = (0.012, 0.016, 0.024, 1)
    bg.inputs["Strength"].default_value = 0.6

    # 只给反射光线的环境：上亮下暗的冷灰渐变，让金属有体积感
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-800, -220)
    sepw = nt.nodes.new("ShaderNodeSeparateXYZ")
    sepw.location = (-600, -220)
    nt.links.new(tc.outputs["Normal"], sepw.inputs["Vector"])
    remap = nt.nodes.new("ShaderNodeMapRange")
    remap.location = (-400, -220)
    remap.inputs["From Min"].default_value = -1.0
    remap.inputs["From Max"].default_value = 1.0
    remap.inputs["To Min"].default_value = 0.0
    remap.inputs["To Max"].default_value = 1.0
    nt.links.new(sepw.outputs["Z"], remap.inputs["Value"])
    sky = nt.nodes.new("ShaderNodeValToRGB")
    sky.location = (-200, -220)
    sky.color_ramp.elements[0].position = 0.0
    sky.color_ramp.elements[1].position = 1.0
    sky_mid = sky.color_ramp.elements.new(0.55)
    if DRAGON:
        # 暖香槟色反射环境，让金铜表面有体积而不是只反黑
        sky.color_ramp.elements[0].color = (0.008, 0.007, 0.006, 1)
        sky.color_ramp.elements[1].color = (0.55, 0.46, 0.33, 1)
        sky_mid.color = (0.12, 0.095, 0.065, 1)
    else:
        sky.color_ramp.elements[0].color = (0.015, 0.02, 0.03, 1)
        sky.color_ramp.elements[1].color = (0.38, 0.46, 0.6, 1)
        sky_mid.color = (0.09, 0.115, 0.16, 1)
    nt.links.new(remap.outputs["Result"], sky.inputs["Fac"])
    env = nt.nodes.new("ShaderNodeBackground")
    env.location = (200, -160)
    env.inputs["Strength"].default_value = 0.75 if DRAGON else 1.2
    nt.links.new(sky.outputs["Color"], env.inputs["Color"])
    lp = nt.nodes.new("ShaderNodeLightPath")
    lp.location = (-200, 320)
    mixw = nt.nodes.new("ShaderNodeMixShader")
    mixw.location = (450, 0)
    nt.links.new(lp.outputs["Is Glossy Ray"], mixw.inputs["Fac"])
    nt.links.new(bg.outputs["Background"], mixw.inputs[1])
    nt.links.new(env.outputs["Background"], mixw.inputs[2])
    nt.links.new(mixw.outputs["Shader"], out.inputs["Surface"])

    setup_cycles(scene)
    setup_compositor(scene)

    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        C.log("[!] AgX look 设置失败，用默认")
    scene.view_settings.exposure = -0.1
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False

    C.log(f"[OK] 摄影棚完成：相机 {tuple(round(v, 2) for v in cam.location)}，"
          f"目标 z={target_z:.3f}，灯光 5 盏，产品台高 {PLINTH_H}")
