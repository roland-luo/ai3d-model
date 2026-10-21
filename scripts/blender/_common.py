"""AI3D 公共函数：项目路径、导入、归一化、网格统计、保存。"""

from __future__ import annotations

import math
import os
import json
import datetime as dt
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

HOME = Path.home()
AI3D = HOME / "ai3d"
PROJECT = os.environ.get("AI3D_PROJECT", "helmet01")
TARGET_SIZE = float(os.environ.get("AI3D_SIZE", "0.35"))  # 最大边，单位米
MODEL_COLLECTION = "AI3D"
STUDIO_COLLECTION = "AI3D_STUDIO"


def log(msg: str) -> None:
    print(f"[AI3D] {msg}", flush=True)


def project_dir() -> Path:
    p = AI3D / "projects" / PROJECT
    p.mkdir(parents=True, exist_ok=True)
    return p


def blend_path() -> Path:
    p = AI3D / "blend"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{PROJECT}.blend"


def render_path() -> Path:
    p = AI3D / "renders"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{PROJECT}_4k.png"


def find_glb() -> Path:
    cands = [
        project_dir() / "model.glb",
        project_dir() / "model" / "model.glb",
    ]
    for c in cands:
        if c.is_file():
            return c
    glbs = sorted(project_dir().rglob("*.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not glbs:
        raise FileNotFoundError(f"{project_dir()} 下没有 GLB，先跑 ComfyUI 的 hy3d")
    return glbs[0]


# --------------------------------------------------------------------------- #
# 集合
# --------------------------------------------------------------------------- #
def ensure_collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def clear_collection(name: str) -> None:
    coll = bpy.data.collections.get(name)
    if coll is None:
        return
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(coll)
    log(f"清空集合 {name}")


def collection_meshes(name: str = MODEL_COLLECTION) -> list[bpy.types.Object]:
    coll = bpy.data.collections.get(name)
    if coll is None:
        return []
    return [o for o in coll.objects if o.type == "MESH"]


def has_mesh() -> bool:
    return bool(collection_meshes())


def model_object() -> bpy.types.Object | None:
    objs = collection_meshes()
    return objs[0] if objs else None


def move_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection) -> None:
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


# --------------------------------------------------------------------------- #
# 导入与归一化
# --------------------------------------------------------------------------- #
def import_glb(path: Path | None = None) -> bpy.types.Object:
    path = path or find_glb()
    clear_collection(MODEL_COLLECTION)
    coll = ensure_collection(MODEL_COLLECTION)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"GLB 里没有网格：{path}")
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
        else:
            move_to_collection(o, coll)
    obj = join_meshes(meshes)
    obj.name = f"{PROJECT}_model"
    log(f"导入 {path.name}：{len(meshes)} 个网格，合并为 {obj.name}")
    return obj


def join_meshes(objs: list[bpy.types.Object]) -> bpy.types.Object:
    objs = [o for o in objs if o and o.name in bpy.data.objects]
    if len(objs) == 1:
        return objs[0]
    target = objs[0]
    try:
        with bpy.context.temp_override(
            active_object=target,
            object=target,
            selected_objects=objs,
            selected_editable_objects=objs,
        ):
            bpy.ops.object.join()
        return target
    except Exception as e:
        log(f"join 失败（{e}），改为逐个合并网格数据")
        return manual_join(objs)


def manual_join(objs: list[bpy.types.Object]) -> bpy.types.Object:
    target = objs[0]
    bm = bmesh.new()
    bm.from_mesh(target.data)
    for o in objs[1:]:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        # 用世界矩阵把顶点搬到 target 的空间
        tmp.transform(target.matrix_world.inverted() @ o.matrix_world)
        me = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        bpy.data.objects.remove(o, do_unlink=True)
    bm.to_mesh(target.data)
    bm.free()
    return target


def bake_world_transform(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.data.transform(mw)
    obj.matrix_world = Matrix.Identity(4)
    obj.data.update()


def mesh_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    vs = [v.co for v in obj.data.vertices]
    if not vs:
        raise RuntimeError("网格是空的")
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def normalize(obj: bpy.types.Object, target: float = TARGET_SIZE,
              center_xy: bool = True, floor: bool = True) -> None:
    bake_world_transform(obj)
    lo, hi = mesh_bounds(obj)
    dims = hi - lo
    longest = max(dims.x, dims.y, dims.z)
    if longest <= 0:
        raise RuntimeError("网格尺寸为 0")
    s = target / longest
    obj.data.transform(Matrix.Scale(s, 4))
    lo, hi = mesh_bounds(obj)
    shift = Vector((0.0, 0.0, 0.0))
    if center_xy:
        shift.x = -(lo.x + hi.x) / 2
        shift.y = -(lo.y + hi.y) / 2
    if floor:
        shift.z = -lo.z
    obj.data.transform(Matrix.Translation(shift))
    obj.data.update()
    lo, hi = mesh_bounds(obj)
    log(f"归一化：缩放 {s:.4f}，尺寸 {tuple(round(v, 4) for v in (hi - lo))}，底部 z={lo.z:.4f}")


def tri_count(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def mesh_stats(obj: bpy.types.Object) -> dict:
    lo, hi = mesh_bounds(obj)
    me = obj.data
    return {
        "verts": len(me.vertices),
        "edges": len(me.edges),
        "faces": len(me.polygons),
        "tris": tri_count(obj),
        "dims": [round(v, 4) for v in (hi - lo)],
        "min": [round(v, 4) for v in lo],
        "max": [round(v, 4) for v in hi],
        "materials": [m.name for m in me.materials if m],
    }


def count_loose_verts(obj: bpy.types.Object) -> int:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    n = sum(1 for v in bm.verts if not v.link_faces)
    bm.free()
    return n


def activate(obj: bpy.types.Object) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_modifier(obj: bpy.types.Object, name: str) -> None:
    with bpy.context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj], selected_editable_objects=[obj]):
        bpy.ops.object.modifier_apply(modifier=name)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def save_blend(path: Path | None = None) -> None:
    path = path or blend_path()
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)
    log(f"已保存 {path}")


def record_stage(stage: str, extra: dict | None = None) -> None:
    """把 Blender 端每个阶段的版本、网格统计写进项目的 run.json。"""
    path = project_dir() / "run.json"
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["project"] = PROJECT
    data["blender"] = bpy.app.version_string
    data.setdefault("stages", {})
    info = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "blender": bpy.app.version_string,
    }
    obj = model_object()
    if obj is not None:
        try:
            info["mesh"] = mesh_stats(obj)
        except Exception:
            pass
    if extra:
        info.update(extra)
    data["stages"][stage] = info
    runs = []
    for base in (project_dir(), project_dir() / "refs"):
        if base.is_dir():
            runs += [str(p) for p in sorted(base.glob("run_*.json"))]
    if runs:
        data["comfy_runs"] = runs

    # 权重指纹：文件名 + sha256 比“仓库名”更能锁定实际跑的是哪份文件
    weights_file = AI3D / "logs" / "weights_verified.txt"
    if weights_file.is_file():
        weights = []
        for line in weights_file.read_text(encoding="utf-8").splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and len(parts[0]) == 64:
                sha, wpath = parts[0], parts[1].strip()
                weights.append({"file": Path(wpath).name, "sha256": sha})
        if weights:
            data["weights"] = weights
            data.setdefault("weight_sources", {
                "qwen": "abenzerps/Qwen-Image-2.1-Uncensored-Quantized@main (2026-10-20)",
                "hunyuan": "Comfy-Org/hunyuan3D_2.1_repackaged@main (2026-10-20)",
            })

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"记录阶段到 {path}")



def clean_scene_extras() -> None:
    """删掉默认立方体/灯/相机，只要空场景。"""
    for obj in list(bpy.data.objects):
        if obj.type in {"MESH", "LIGHT", "CAMERA"}:
            bpy.data.objects.remove(obj, do_unlink=True)


def smooth_by_angle(obj: bpy.types.Object, degrees: float = 35.0) -> None:
    activate(obj)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(degrees))
        log(f"shade_smooth_by_angle {degrees}°")
    except Exception as e:
        log(f"shade_smooth_by_angle 不可用（{e}），退回按面平滑")
        for p in obj.data.polygons:
            p.use_smooth = True
