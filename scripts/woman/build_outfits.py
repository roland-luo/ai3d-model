"""Colour, optionally re-hair, and export one standalone GLB per outfit.

The three Quaternius source models share the same face/rig but have different
clothing.  Keeping them as separate GLBs is deliberate: the web viewer swaps
whole outfits.  Re-binding meshes between armatures produced double-scale
artefacts, so each outfit keeps its own original skeleton.
"""
import bpy
import sys
import math
from pathlib import Path
from mathutils import Vector

PROJECT = Path("/home/roland/ai3d/projects/woman01")
MODELS = PROJECT / "refs" / "models"
OUT = PROJECT / "viewer" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

SKIN_TONE = (0.50, 0.315, 0.225, 1.0)
PALETTE = {
    "LimeGreen": (0.76, 0.735, 0.68, 1.0),
    "Gold": (0.45, 0.29, 0.085, 1.0),
    "Red": (0.030, 0.019, 0.013, 1.0),
    "White": (0.72, 0.70, 0.64, 1.0),
    "Orange": (0.30, 0.19, 0.105, 1.0),
    "Grey": (0.62, 0.60, 0.55, 1.0),
    "Hair_Blond": (0.030, 0.019, 0.013, 1.0),
    "Hair_Brown": (0.028, 0.017, 0.012, 1.0),
    "LightGreen": (0.20, 0.235, 0.12, 1.0),
    "Green": (0.095, 0.12, 0.055, 1.0),
    "Brown2": (0.12, 0.085, 0.05, 1.0),
    "Brown_02": (0.055, 0.04, 0.028, 1.0),
    "Brown": (0.014, 0.010, 0.008, 1.0),
    "Skin": SKIN_TONE,
}
ROUGHNESS = {"Skin": 0.62, "Red": 0.46, "Hair_Blond": 0.40, "Hair_Brown": 0.40,
             "Gold": 0.34, "Brown": 0.30}


def remove(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def recolour():
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        base = mat.name.split(".")[0]
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if not bsdf:
            continue
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = ROUGHNESS.get(base, 0.60)
        if base in PALETTE:
            bsdf.inputs["Base Color"].default_value = PALETTE[base]
        if base == "Skin":
            bsdf.inputs["Subsurface Weight"].default_value = 0.03
        if base in ("LimeGreen", "White"):
            try:
                bsdf.inputs["Sheen Weight"].default_value = 0.16
            except Exception:
                pass
        mat.diffuse_color = bsdf.inputs["Base Color"].default_value


def make_hair_material():
    mat = bpy.data.materials.new("Hair_Long")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.060, 0.034, 0.020, 1)
    bsdf.inputs["Roughness"].default_value = 0.32
    try:
        bsdf.inputs["Coat Weight"].default_value = 0.12
        bsdf.inputs["Coat Roughness"].default_value = 0.22
    except Exception:
        pass
    mat.diffuse_color = (0.060, 0.034, 0.020, 1)
    return mat


def curve_lock(name, pts, depths, radius_scale=1.0, mat=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 2
    cu.bevel_depth = depths
    cu.bevel_resolution = 0
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, (co, rad) in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
        bp.radius = rad * radius_scale
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.object
    ob.data.materials.append(mat)
    return ob


def add_long_hair(arm, head):
    """Long low-poly hair, rigid-skinned to the Head bone."""
    # head bounds in rest pose
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = head.evaluated_get(dg)
    me = ev.to_mesh()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for v in me.vertices:
        w = ev.matrix_world @ v.co
        lo = Vector((min(lo[i], w[i]) for i in range(3)))
        hi = Vector((max(hi[i], w[i]) for i in range(3)))
    ev.to_mesh_clear()
    arm.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    top = hi.z
    cx = (lo.x + hi.x) * 0.5
    print("HAIR head bounds", tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))

    mat = make_hair_material()
    pieces = []

    # Back sheet: the mass of hair falling behind the shoulders.
    verts = []
    faces = []
    rows = 12
    cols = 7
    for r in range(rows):
        v = r / (rows - 1)
        for c in range(cols):
            u = -1 + 2 * c / (cols - 1)
            width = 0.072 + 0.048 * v
            x = cx + u * width
            y = 0.072 + 0.045 * v + 0.010 * math.cos(u * 1.6)
            z = top - 0.035 - 0.50 * v + 0.018 * math.sin(u * 3.1) * v
            # wavy tip
            z += 0.018 * math.sin(u * 5.0 + 0.6) * (v ** 3)
            verts.append((x, y, z))
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = r * cols + c
            faces.append((a, a + 1, a + cols + 1, a + cols))
    sheet_me = bpy.data.meshes.new("HairSheet")
    sheet_me.from_pydata(verts, [], faces)
    sheet_me.validate()
    sheet_me.update()
    sheet = bpy.data.objects.new("HairSheet", sheet_me)
    bpy.context.scene.collection.objects.link(sheet)
    sheet.data.materials.append(mat)
    pieces.append(sheet)

    # Back locks, with a slight outward sway.
    xs = [-0.085, -0.058, -0.030, 0.0, 0.030, 0.058, 0.085]
    for idx, x in enumerate(xs):
        spread = 1.0 + 0.35 * abs(x) / 0.085
        length = 0.52 + 0.04 * math.sin(idx * 2.1)
        pts = [
            ((cx + x * 0.55, 0.052, top - 0.020), 1.0),
            ((cx + x * 0.90, 0.095, top - 0.18), 0.95),
            ((cx + x * spread, 0.112, top - 0.34), 0.72),
            ((cx + x * spread * 1.10, 0.095, top - length), 0.22),
        ]
        pieces.append(curve_lock(f"Lock{idx}", pts, 0.016, 1.0, mat))

    # Front side locks framing the face (in front = -Y).
    for side in (-1, 1):
        pts = [
            ((cx + side * 0.095, -0.012, top - 0.080), 1.0),
            ((cx + side * 0.115, -0.042, top - 0.20), 0.9),
            ((cx + side * 0.116, -0.036, top - 0.34), 0.55),
            ((cx + side * 0.098, -0.018, top - 0.44), 0.15),
        ]
        pieces.append(curve_lock(f"Front{side}", pts, 0.012, 1.0, mat))
    # join
    bpy.ops.object.select_all(action="DESELECT")
    for p in pieces:
        p.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    bpy.ops.object.join()
    hair = bpy.context.object
    hair.name = "LongHair"
    for poly in hair.data.polygons:
        poly.use_smooth = True

    # move mesh data into armature local space, share the armature transform
    me = hair.data
    me.transform(arm.matrix_world.inverted())
    hair.parent = arm
    hair.matrix_parent_inverse.identity()
    hair.matrix_basis.identity()
    hair.matrix_world = arm.matrix_world
    mod = hair.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    vg = hair.vertex_groups.get("Head") or hair.vertex_groups.new(name="Head")
    vg.add(range(len(me.vertices)), 1.0, "REPLACE")
    print("HAIR added", len(me.vertices), "verts")


def build(prefix, src, add_hair=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src))
    for o in list(bpy.context.scene.objects):
        if o.type == "MESH" and o.name.startswith("Icosphere"):
            remove(o)
    arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    head = next((o for o in meshes if "Head" in o.name), None)
    recolour()

    # keep only Idle_Neutral, rename it Idle
    idle = None
    for a in bpy.data.actions:
        if "Idle_Neutral" in a.name:
            idle = a
            break
    for a in list(bpy.data.actions):
        if a != idle:
            bpy.data.actions.remove(a)
    idle.name = "Idle"
    if not arm.animation_data:
        arm.animation_data_create()
    arm.animation_data.action = idle
    try:
        if hasattr(idle, "slots") and len(idle.slots):
            arm.animation_data.action_slot = idle.slots[0]
    except Exception as e:
        print("slot warn", e)

    if add_hair and head:
        add_long_hair(arm, head)

    bpy.context.scene.frame_set(12)
    for o in meshes:
        o.hide_set(False)
        o.hide_render = False
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    for o in meshes:
        o.select_set(True)
    hair = bpy.data.objects.get("LongHair")
    if hair:
        hair.select_set(True)
    bpy.context.view_layer.objects.active = arm
    path = OUT / f"outfit_{prefix}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_apply=False,
        export_yup=True,
    )
    print("EXPORTED", path, path.stat().st_size)
    # save a per-outfit source blend
    blend = PROJECT / f"{prefix}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print("SAVED", blend)


def main():
    which = sys.argv[sys.argv.index("--") + 1:] or ["dress", "casual", "adventurer"]
    mapping = {
        "dress": ("dress", MODELS / "anim3.glb", True),
        "casual": ("casual", MODELS / "anim2.glb", False),
        "adventurer": ("adventurer", MODELS / "adventurer.glb", False),
    }
    for key in which:
        prefix, src, hair = mapping[key]
        print("\n=====", prefix, "=====")
        build(prefix, src, hair)


if __name__ == "__main__":
    main()
