"""Build one swappable low-poly character from three CC0 Quaternius outfits.

All three source GLBs share the same 62-bone rig.  We keep the Formal armature
as the master and re-bind the Casual / Adventurer meshes to it, so a single
skeleton and a single idle clip drives every outfit.

Run:
  blender -b --python build_character.py -- <out.blend> <out.glb>
"""
import bpy
import sys
import math
from pathlib import Path
from mathutils import Vector

PROJECT = Path("/home/roland/ai3d/projects/woman01")
MODELS = PROJECT / "refs" / "models"
SRC = [
    ("Dress", MODELS / "anim3.glb"),
    ("Casual", MODELS / "anim2.glb"),
    ("Adventurer", MODELS / "adventurer.glb"),
]

SKIN_TONE = (0.50, 0.315, 0.225, 1.0)

# base material name -> linear RGBA
PALETTE = {
    # dress outfit
    "LimeGreen": (0.76, 0.735, 0.68, 1.0),   # ivory dress
    "Gold": (0.45, 0.29, 0.085, 1.0),
    "Red": (0.030, 0.019, 0.013, 1.0),       # hair + shoes in the formal model
    # casual outfit
    "White": (0.72, 0.70, 0.64, 1.0),
    "Orange": (0.30, 0.19, 0.105, 1.0),
    "Grey": (0.62, 0.60, 0.55, 1.0),
    "Hair_Blond": (0.030, 0.019, 0.013, 1.0),
    "Hair_Brown": (0.028, 0.017, 0.012, 1.0),
    # adventurer / common
    "LightGreen": (0.20, 0.235, 0.12, 1.0),
    "Green": (0.095, 0.12, 0.055, 1.0),
    "Brown2": (0.12, 0.085, 0.05, 1.0),
    "Brown_02": (0.055, 0.04, 0.028, 1.0),
    "Brown": (0.014, 0.010, 0.008, 1.0),     # eyes / brows / laces
    "Skin": SKIN_TONE,
}

ROUGHNESS = {"Skin": 0.62, "Red": 0.48, "Hair_Blond": 0.42, "Hair_Brown": 0.42,
             "Gold": 0.34, "Brown": 0.30}

MASTER_NAME = "CharacterArmature"


def remove(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_outfit(prefix, path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    meshes = [o for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")]
    aux = [o for o in new if o.type == "MESH" and o.name.startswith("Icosphere")]
    for o in aux:
        remove(o)
    for o in meshes:
        old = o.name
        o.name = f"{prefix}_{old.replace('Formad', 'Formal').replace('Formal_', '').replace('Casual_', '').replace('Adventurer_', '')}"
    print(f"[{prefix}] armature={arm.name} meshes={[o.name for o in meshes]}")
    return arm, meshes


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out_blend = Path(args[0])
    out_glb = Path(args[1])

    clear_scene()
    outfits = {}
    for prefix, path in SRC:
        outfits[prefix] = import_outfit(prefix, path)

    master_arm, master_meshes = outfits["Dress"]
    master_arm.name = MASTER_NAME
    master_world = master_arm.matrix_world.copy()
    master_root = master_arm.parent

    # make sure the master root sits on the floor
    bpy.context.view_layer.update()

    # Rebind every other outfit to the master armature.
    for prefix, (arm, meshes) in outfits.items():
        if prefix == "Dress":
            continue
        for mesh in meshes:
            world = mesh.matrix_world.copy()
            for mod in list(mesh.modifiers):
                if mod.type == "ARMATURE":
                    mesh.modifiers.remove(mod)
            mesh.parent = None
            mesh.matrix_world = master_world.copy()
            mesh.matrix_parent_inverse = master_arm.matrix_world.inverted()
            mesh.parent = master_arm
            mod = mesh.modifiers.new("Armature", "ARMATURE")
            mod.object = master_arm
            print(f"rebound {mesh.name} from {arm.name}")
        remove(arm)
        # remove the outfit's now-empty root node if it is separate
        for o in list(bpy.data.objects):
            if o.type == "EMPTY" and o.name == "RootNode" and o != master_root and not o.children:
                remove(o)

    # remove any leftover non-master armatures
    for o in list(bpy.data.objects):
        if o.type == "ARMATURE" and o != master_arm:
            remove(o)
    for o in list(bpy.data.objects):
        if o.type == "EMPTY" and o.name == "RootNode" and o != master_root:
            remove(o)

    all_meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    print("FINAL MESHES", [o.name for o in all_meshes])

    # palette
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
                bsdf.inputs["Sheen Weight"].default_value = 0.18
            except Exception:
                pass
        mat.name = base if base != "LimeGreen" else "Dress"
        mat.diffuse_color = bsdf.inputs["Base Color"].default_value

    # rename dress material properly (name it Dress for the viewer)
    for mat in bpy.data.materials:
        if mat.name == "Dress":
            pass

    # keep one idle action, remove the rest
    idle = None
    for act in bpy.data.actions:
        if "Idle_Neutral" in act.name:
            idle = act
            break
    for act in list(bpy.data.actions):
        if act != idle:
            bpy.data.actions.remove(act)
    if idle:
        idle.name = "Idle"
        if not master_arm.animation_data:
            master_arm.animation_data_create()
        master_arm.animation_data.action = idle
        try:
            if hasattr(idle, "slots") and len(idle.slots):
                master_arm.animation_data.action_slot = idle.slots[0]
        except Exception as e:
            print("slot warn", e)
        bpy.context.scene.frame_set(12)
        print("ACTION kept:", idle.name)

    # set up collections for the three outfits
    for prefix, (arm, meshes) in outfits.items():
        coll = bpy.data.collections.new(prefix)
        bpy.context.scene.collection.children.link(coll)
        for mesh in meshes:
            for c in list(mesh.users_collection):
                c.objects.unlink(mesh)
            coll.objects.link(mesh)
        if prefix == "Dress":
            for c in list(master_arm.users_collection):
                c.objects.unlink(master_arm)
            coll.objects.link(master_arm)

    # only the white dress is visible in the saved file / first render
    for prefix in ("Casual", "Adventurer"):
        for mesh in outfits[prefix][1]:
            mesh.hide_set(True)
            mesh.hide_render = True

    # ensure the master root is on the floor
    if master_root:
        master_root.location.z = 0.0

    # save .blend
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    print("SAVED", out_blend)

    # export all meshes + armature in one GLB, with the full outfit set
    for o in bpy.data.objects:
        o.hide_set(False)
        o.hide_render = False
    bpy.ops.object.select_all(action="DESELECT")
    master_arm.select_set(True)
    for mesh in all_meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = master_arm
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out_glb),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_apply=False,
        export_yup=True,
    )
    print("EXPORTED", out_glb, out_glb.stat().st_size)


if __name__ == "__main__":
    main()
