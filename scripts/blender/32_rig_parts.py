"""AI3D 32_rig_parts.py — 给分件模型搭第一版“部件级骨架”（配置驱动）。

输入是一份 rig.json（例如 projects/dragon01/rig.json），里面描述：
- 哪个件是身体、哪个件是头/角/鬃毛/腿；
- 每根骨叫什么、父级是谁、枢轴从哪个切口取；
- 哪些件要在身体上做测地线渐变、半径多少；
- 哪些件是龙须、分几段、折线从哪来；
- 姿态预览和 GLB 验收要测什么。

脚本本身不再写死“龙”的部件名。换模型时只改 rig.json，不用改代码。
身体仍然是整块刚性绑定；要沿脊柱弯曲，先重拓扑，见
projects/dragon01/rig/README.md。

用法：
    ~/.local/bin/blender -b projects/dragon01/parts/dragon01_parts.blend \
      --python scripts/blender/32_rig_parts.py -- \
      --config projects/dragon01/rig.json \
      --out projects/dragon01/rig

也可以不先打开分件工程，让脚本自己开（仅后台模式）：
    ~/.local/bin/blender -b --python scripts/blender/32_rig_parts.py -- \
      --config projects/dragon01/rig.json

产物：
    <out>/<file_stem>.blend
    <out>/rig_manifest.json
    <out>/glb/<file_stem>.glb
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector, kdtree

HOME = Path.home()


def log(msg: str) -> None:
    print(f"[AI3D rig] {msg}", flush=True)


def die(msg: str) -> None:
    raise SystemExit(f"[×] {msg}")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description="AI3D 分件骨架（配置驱动）")
    ap.add_argument("--config", default=None,
                    help="rig.json；也接受旧的 parts.json（自动找同目录 rig.json）")
    ap.add_argument("--out", default=None, help="输出目录，默认 <project>/rig")
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} 不是合法 JSON：第 {e.lineno} 行 {e.msg}")


def is_rig_config(data: dict) -> bool:
    return isinstance(data.get("body"), dict) and isinstance(data.get("rigid"), list)


def resolve_rig_config(config_path: str | None) -> tuple[Path, dict]:
    """返回 (rig.json 路径, 配置)。兼容旧的 parts.json 参数。"""
    if config_path:
        path = Path(config_path).expanduser().resolve()
        if not path.is_file():
            die(f"找不到配置：{path}")
        data = read_json(path)
        if is_rig_config(data):
            return path, data
        # 旧命令传的是 parts.json：自动找同目录 rig.json
        sibling = path.parent / "rig.json"
        if sibling.is_file():
            log(f"{path.name} 是分件配置，自动改用 {sibling.name}")
            return sibling, read_json(sibling)
        die(f"{path.name} 不是 rig.json；同目录也没有 rig.json。"
            "请先写一份骨架配置，格式见 projects/dragon01/rig.json")

    project = os.environ.get("AI3D_PROJECT")
    if project:
        p = Path(project).expanduser()
        base = p if p.is_absolute() else (HOME / "ai3d" / "projects" / p)
        path = base / "rig.json"
        if path.is_file():
            return path, read_json(path)
        die(f"{path} 不存在。设置 AI3D_PROJECT 或显式传 --config")

    die("请用 --config 指定 rig.json，或设置 AI3D_PROJECT")


def project_dir(rig_path: Path) -> Path:
    project = os.environ.get("AI3D_PROJECT")
    if project:
        p = Path(project).expanduser()
        return p if p.is_absolute() else (HOME / "ai3d" / "projects" / p)
    return rig_path.parent


def resolve_parts_config(cfg: dict, rig_path: Path) -> dict:
    name = cfg.get("parts_config")
    if not name:
        return {}
    path = (rig_path.parent / name).resolve()
    if not path.is_file():
        log(f"⚠ 找不到分件配置 {path}；龙须胶囊折线会退回包围盒对角线")
        return {}
    return read_json(path)


def resolve_source_blend(cfg: dict, pdir: Path) -> Path:
    raw = cfg.get("source_blend")
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (pdir / p).resolve()
    guesses = [
        pdir / "parts" / f"{pdir.name}_parts.blend",
        pdir / "parts" / "parts.blend",
    ]
    for p in guesses:
        if p.is_file():
            return p
    found = sorted((pdir / "parts").glob("*.blend"))
    return found[0] if found else guesses[0]


def part_names(cfg: dict) -> list[str]:
    names = [cfg["body"]["part"]]
    names += [e["part"] for e in cfg.get("rigid", [])]
    names += [w["part"] for w in cfg.get("whiskers", [])]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        die(f"rig.json 里同一个件被写了多次：{dup}")
    return names


# --------------------------------------------------------------------------- #
# 几何工具
# --------------------------------------------------------------------------- #
def world_vertices(obj: bpy.types.Object) -> list[Vector]:
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def bounds(points: list[Vector]) -> tuple[Vector, Vector]:
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo, hi


def centroid(points: list[Vector]) -> Vector:
    c = Vector((0, 0, 0))
    for p in points:
        c += p
    return c / max(1, len(points))


def closest_pair(a: list[Vector], b: list[Vector]) -> tuple[float, int, int]:
    kd = kdtree.KDTree(len(b))
    for i, p in enumerate(b):
        kd.insert(p, i)
    kd.balance()
    best = (1e9, -1, -1)
    for i, p in enumerate(a):
        _, j, d = kd.find(p)
        if d < best[0]:
            best = (d, i, j)
    return best


def shared_centroid(a: list[Vector], b: list[Vector], tol: float = 1e-4) -> tuple[Vector, int, str]:
    """两件在切口上共享的顶点（坐标重合）的中心；没有共享就退回最近点中点。"""
    kd = kdtree.KDTree(len(b))
    for i, p in enumerate(b):
        kd.insert(p, i)
    kd.balance()
    hits = [p for p in a if kd.find_range(p, tol)]
    if hits:
        return centroid(hits), len(hits), "shared"
    d, i, j = closest_pair(a, b)
    return (a[i] + b[j]) * 0.5, 0, "nearest"


def far_from(points: list[Vector], pivot: Vector) -> int:
    return max(range(len(points)), key=lambda i: (points[i] - pivot).length)


def ensure_len(head: Vector, tail: Vector, minimum: float, fallback_dir: Vector) -> Vector:
    if (tail - head).length < minimum:
        d = tail - head
        if d.length < 1e-6:
            d = fallback_dir
        return head + d.normalized() * minimum
    return tail


def add_bone(arm_data, name: str, head: Vector, tail: Vector, parent=None, connect=False):
    if name in arm_data.edit_bones:
        die(f"骨头重名：{name}")
    eb = arm_data.edit_bones.new(name)
    eb.head = head
    eb.tail = tail
    if parent:
        parent_bone = arm_data.edit_bones.get(parent)
        if parent_bone is None:
            die(f"骨头 {name} 的父级 {parent} 还不存在；请把父级写在它前面")
        eb.parent = parent_bone
        eb.use_connect = bool(connect)
    eb.use_deform = True
    return eb


def resample_polyline(pts: list[Vector], n: int) -> list[Vector]:
    """按弧长把折线重采样成 n+1 个点（包含两端）。"""
    if n < 1:
        die("resample 段数必须 >= 1")
    if len(pts) < 2:
        return [pts[0].copy() for _ in range(n + 1)]
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seg)
    if total < 1e-9:
        return [pts[0].copy() for _ in range(n + 1)]
    out = [pts[0].copy()]
    target_step = total / n
    acc = 0.0
    target = target_step
    i = 0
    while i < len(seg) and len(out) < n:
        if acc + seg[i] >= target:
            t = (target - acc) / max(seg[i], 1e-12)
            out.append(pts[i].lerp(pts[i + 1], t))
            target += target_step
        else:
            acc += seg[i]
            i += 1
    out.append(pts[-1].copy())
    return out


def point_polyline_param(p: Vector, pts: list[Vector]) -> tuple[float, float]:
    """返回 (最近点弧长, 距离)。"""
    best_s = 0.0
    best_d = 1e9
    acc = 0.0
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]
        ab = b - a
        length = ab.length
        if length < 1e-12:
            continue
        t = max(0.0, min(1.0, (p - a).dot(ab) / (length * length)))
        q = a + ab * t
        d = (p - q).length
        if d < best_d:
            best_d = d
            best_s = acc + length * t
        acc += length
    return best_s, best_d


def shared_indices(target: list[Vector], other: list[Vector], tol: float = 1e-4) -> list[int]:
    """target 里与 other 有重合顶点的下标（切口环）。"""
    kd = kdtree.KDTree(len(other))
    for i, p in enumerate(other):
        kd.insert(p, i)
    kd.balance()
    return [i for i, p in enumerate(target) if kd.find_range(p, tol)]


def dijkstra_multi(adj, co: list[Vector], sources: list[int], max_dist: float) -> list[float]:
    """从多个源点沿网格边生长，返回每个顶点的距离（超过 max_dist 为 inf）。"""
    n = len(co)
    dist = [float("inf")] * n
    h = []
    for s in sources:
        dist[s] = 0.0
        h.append((0.0, s))
    heapq.heapify(h)
    while h:
        d, a = heapq.heappop(h)
        if d > dist[a] + 1e-12:
            continue
        for b in adj[a]:
            nd = d + (co[a] - co[b]).length
            if nd <= max_dist and nd < dist[b]:
                dist[b] = nd
                heapq.heappush(h, (nd, b))
    return dist


def polyline_length(pts: list[Vector]) -> float:
    return sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def whisker_weights(pts: list[Vector], poly: list[Vector], n_bones: int):
    """给每个顶点返回 {bone_index: weight}。

    过渡只发生在关节“之后”，而不是关节两侧各一半。原因是龙须 A 在
    靠近嘴的根部有一个独立小岛（源模型自带约 7 mm 缺口）：如果根部顶点
    也吃下一根骨的权重，转头/弯须时小岛会和主须分开得更明显。现在根部
    整段 100% 跟第一根骨，主须从小岛后面才开始渐变。
    """
    length = polyline_length(poly)
    seg = length / n_bones
    blend = min(0.018, seg * 0.55)
    out = []
    for p in pts:
        s, _ = point_polyline_param(p, poly)
        s = max(0.0, min(length, s))
        j = min(n_bones - 1, max(0, int(s / max(seg, 1e-9))))
        if j == 0:
            out.append({0: 1.0})
            continue
        start = j * seg
        t = smoothstep((s - start) / max(blend, 1e-9))
        if t >= 1.0:
            out.append({j: 1.0})
        else:
            out.append({j - 1: 1.0 - t, j: t})
    return out


def surface_path(pts: list[Vector], edges) -> tuple[list[Vector], float]:
    """在网格表面找最远点对，回溯一条边路径。"""
    adj = [[] for _ in range(len(pts))]
    for e in edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)

    def dij(src):
        dist = [float("inf")] * len(pts)
        prev = [-1] * len(pts)
        dist[src] = 0.0
        h = [(0.0, src)]
        while h:
            d, a = heapq.heappop(h)
            if d > dist[a] + 1e-12:
                continue
            for b in adj[a]:
                nd = d + (pts[a] - pts[b]).length
                if nd < dist[b]:
                    dist[b] = nd
                    prev[b] = a
                    heapq.heappush(h, (nd, b))
        return dist, prev

    corner = min(range(len(pts)), key=lambda i: (pts[i] - Vector((1, 1, 1))).length)
    d0, _ = dij(corner)
    a0 = max(range(len(pts)), key=lambda i: d0[i])
    d1, prev1 = dij(a0)
    b0 = max(range(len(pts)), key=lambda i: d1[i])
    path = [b0]
    while path[-1] != a0 and prev1[path[-1]] != -1:
        path.append(prev1[path[-1]])
    path.reverse()
    return [pts[i] for i in path], d1[b0]


# --------------------------------------------------------------------------- #
# 场景准备
# --------------------------------------------------------------------------- #
def current_parts() -> dict[str, bpy.types.Object]:
    return {o.name: o for o in bpy.data.objects if o.get("ai3d_part")}


def ensure_parts_scene(cfg: dict, rig_path: Path, names: list[str]) -> dict[str, bpy.types.Object]:
    parts = current_parts()
    missing = [n for n in names if n not in parts]
    if not missing:
        return parts
    if parts:
        die(f"当前场景只有部分件，缺少 {missing}。请打开完整的分件工程。")

    pdir = project_dir(rig_path)
    source = resolve_source_blend(cfg, pdir)
    if not bpy.app.background:
        die(f"当前场景没有分件。请先打开：{source}\n"
            "或在后台运行：blender -b <分件工程> --python 32_rig_parts.py -- --config rig.json")
    if not source.is_file():
        die(f"当前场景没有分件，也找不到源工程：{source}\n"
            "请在 rig.json 的 source_blend 里写对路径")
    log(f"当前场景没有分件，自动打开 {source}")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    parts = current_parts()
    missing = [n for n in names if n not in parts]
    if missing:
        die(f"分件工程里缺少 {missing}\n现有的带 ai3d_part 标记的对象：{sorted(parts)}")
    return parts


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run(config_path: str | None = None, out_dir: str | None = None,
        export: bool = True, save: bool = True) -> dict:
    rig_path, cfg = resolve_rig_config(config_path)
    pdir = project_dir(rig_path)
    out = Path(out_dir).expanduser().resolve() if out_dir else (pdir / "rig")
    out.mkdir(parents=True, exist_ok=True)

    body_cfg = cfg["body"]
    rigid_cfg = cfg.get("rigid", [])
    whisker_cfg = cfg.get("whiskers", [])
    names = part_names(cfg)
    parts = ensure_parts_scene(cfg, rig_path, names)
    parts_cfg = resolve_parts_config(cfg, rig_path)

    source_blend = bpy.data.filepath
    W = {n: world_vertices(parts[n]) for n in names}
    for n in names:
        if not W[n]:
            die(f"分件 {n} 没有顶点")
    B = {n: bounds(W[n]) for n in names}
    log(f"分件 {len(names)} 个；输出 {out}")

    # ---------- 骨架 ----------
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    coll = bpy.data.collections.get(cfg.get("collection", "")) or bpy.context.scene.collection
    rig_name = cfg.get("rig_name", "Rig")

    # 幂等：删掉旧骨架和旧空物体。旧骨架用 ai3d_rig 标记识别。
    for obj in list(bpy.data.objects):
        if obj.type == "ARMATURE" and (obj.get("ai3d_rig") or obj.name == rig_name):
            log(f"删除旧骨架 {obj.name}")
            bpy.data.objects.remove(obj, do_unlink=True)
    for name in cfg.get("cleanup_objects", []):
        old = bpy.data.objects.get(name)
        if old:
            log(f"删除旧空物体 {name}")
            bpy.data.objects.remove(old, do_unlink=True)

    arm_data = bpy.data.armatures.new(rig_name)
    arm = bpy.data.objects.new(rig_name, arm_data)
    coll.objects.link(arm)
    arm.show_in_front = True
    arm_data.display_type = "OCTAHEDRAL"
    arm["ai3d_rig"] = rig_name

    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    root_cfg = cfg.get("root", {})
    root_bone = root_cfg.get("bone", "root")
    root_head = Vector(root_cfg.get("head", [0, 0, 0]))
    add_bone(arm_data, root_bone, root_head,
             root_head + Vector((0, 0, float(root_cfg.get("length_m", 0.05)))))

    body_part = body_cfg["part"]
    body_bone = body_cfg.get("bone", "body")
    body_lo, body_hi = B[body_part]
    body_c = (body_lo + body_hi) * 0.5
    body_head = Vector((body_c.x, body_c.y, body_lo.z))
    add_bone(arm_data, body_bone, body_head,
             body_head + Vector((0, 0, float(body_cfg.get("length_m", 0.12)))),
             parent=body_cfg.get("parent", root_bone))
    log(f"{body_part} -> {body_bone}（整体控制骨）")

    part_bone: dict[str, str] = {body_part: body_bone}
    rigid_info: dict[str, dict] = {}
    for e in rigid_cfg:
        part = e["part"]
        bone = e.get("bone", part)
        parent = e.get("parent", body_bone)
        pivot_from = e.get("pivot_from", body_part)
        if pivot_from not in W:
            die(f"{part} 的 pivot_from={pivot_from} 不是已定义的件")
        pivot, n_shared, mode = shared_centroid(W[part], W[pivot_from])
        tail_mode = e.get("tail", "farthest")
        if tail_mode == "bounds_center":
            target = (B[part][0] + B[part][1]) * 0.5
        elif tail_mode == "farthest":
            target = W[part][far_from(W[part], pivot)]
        elif tail_mode == "vector":
            target = pivot + Vector(e["tail_vector"])
        else:
            die(f"{part} 的 tail 只能是 bounds_center / farthest / vector，实际 {tail_mode}")
        min_len = float(e.get("min_length_m", 0.025))
        fallback = Vector(e.get("fallback_dir", [0, 0, 1]))
        add_bone(arm_data, bone, pivot, ensure_len(pivot, target, min_len, fallback), parent=parent)
        part_bone[part] = bone
        rigid_info[part] = {
            "bone": bone,
            "parent": parent,
            "pivot": [round(float(x), 5) for x in pivot],
            "shared_vertices": n_shared,
            "shared_mode": mode,
        }
        if "blend_radius_m" in e:
            rigid_info[part]["blend_radius_m"] = float(e["blend_radius_m"])
        log(f"{part} -> {bone}；枢轴 {tuple(round(x, 4) for x in pivot)}"
            f"（共享点 {n_shared}，{mode}；父级 {parent}）")

    whisker_bones: dict[str, tuple[list[str], list[Vector], list[Vector]]] = {}
    whisker_info: dict[str, dict] = {}
    for w in whisker_cfg:
        part = w["part"]
        prefix = w.get("prefix", part)
        segments = int(w.get("segments", 3))
        if segments < 1:
            die(f"{part} 的 segments 必须 >= 1")
        mode = w.get("polyline", "capsule")
        poly: list[Vector] | None = None

        if w.get("points"):
            poly = [Vector(p) for p in w["points"]]
        elif mode == "capsule":
            entry = next((p for p in parts_cfg.get("parts", [])
                          if p.get("id") == part), None)
            pts = (entry or {}).get("capsule", {}).get("points")
            if pts:
                poly = [Vector(p) for p in pts]
                log(f"{part} 用胶囊折线 {len(poly)} 点")
            else:
                lo, hi = B[part]
                poly = [lo, hi]
                log(f"⚠ {part} 没读到胶囊折线，退回包围盒对角线")
        elif mode == "surface_path":
            samples = int(w.get("samples", 12))
            path, length = surface_path(W[part], parts[part].data.edges)
            poly = resample_polyline(path, samples)
            log(f"{part} 表面路径 {round(length * 100, 2)} cm，重采样 {samples} 点")
        else:
            die(f"{part} 的 polyline 只能是 capsule / surface_path，或直接给 points")

        orient_to = w.get("orient_to")
        if orient_to:
            if orient_to not in W:
                die(f"{part} 的 orient_to={orient_to} 不是已定义的件")
            anchor, _, _ = shared_centroid(W[part], W[orient_to])
            if (poly[0] - anchor).length > (poly[-1] - anchor).length:
                poly.reverse()

        joints = resample_polyline(poly, segments)
        parent = w.get("parent", "head")
        bone_names = []
        for i in range(segments):
            name = f"{prefix}_{i + 1}"
            add_bone(arm_data, name, joints[i], joints[i + 1],
                     parent=parent if i == 0 else bone_names[-1], connect=(i > 0))
            bone_names.append(name)
        whisker_bones[part] = (bone_names, poly, joints)
        part_bone[part] = bone_names[0]
        whisker_info[part] = {
            "bones": bone_names,
            "segments": segments,
            "parent": parent,
            "polyline": [[round(float(x), 5) for x in p] for p in poly],
        }
        log(f"{part} 骨架：{bone_names}（父级 {parent}）")

    bpy.ops.object.mode_set(mode="OBJECT")
    log(f"骨架完成：{len(arm_data.bones)} 根骨")

    # ---------- 绑定 ----------
    for name in names:
        obj = parts[name]
        mw = obj.matrix_world.copy()
        obj.parent = arm
        obj.matrix_parent_inverse = arm.matrix_world.inverted()
        obj.matrix_world = mw
        obj.vertex_groups.clear()
        for m in list(obj.modifiers):
            if m.type == "ARMATURE":
                obj.modifiers.remove(m)
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        mod.use_vertex_groups = True

        if name in whisker_bones:
            bones, poly, _ = whisker_bones[name]
            weights = whisker_weights(W[name], poly, len(bones))
            groups = [obj.vertex_groups.new(name=b) for b in bones]
            for vi, w in enumerate(weights):
                for bi, val in w.items():
                    if val > 1e-6:
                        groups[bi].add([vi], float(val), "REPLACE")
            log(f"绑定 {name:20s} -> {bones}（{len(W[name])} 顶点，平滑权重）")
        else:
            bone = part_bone[name]
            vg = obj.vertex_groups.new(name=bone)
            vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
            log(f"绑定 {name:20s} -> {bone}（{len(obj.data.vertices)} 顶点，刚性）")

    # ---------- 身体切口渐变 ----------
    # 身体仍是 body 骨主导，但在头/腿切口附近把权重按测地距离柔和地分给
    # 对应骨头。这样头转 20° 时，脖子会跟着弯一点，而不是直接裂开。
    body = parts[body_part]
    body_pts = W[body_part]
    body_adj = [[] for _ in range(len(body_pts))]
    for e in body.data.edges:
        a, b = e.vertices
        body_adj[a].append(b)
        body_adj[b].append(a)

    raw: dict[int, dict[str, float]] = {}
    blend_stats = []
    blend_targets: list[str] = []
    for e in rigid_cfg:
        radius = e.get("blend_radius_m")
        if not radius:
            continue
        part = e["part"]
        bone = part_bone[part]
        cut = shared_indices(body_pts, W[part])
        if not cut:
            log(f"⚠ {part} 与身体没有共享切口顶点，跳过渐变")
            continue
        dist = dijkstra_multi(body_adj, body_pts, cut, float(radius))
        touched = 0
        for vi, d in enumerate(dist):
            if d >= radius or d == float("inf"):
                continue
            # 余弦衰减：切口处 1，半径处 0，一阶导也连续
            w = 0.5 * (1.0 + math.cos(math.pi * min(1.0, d / radius)))
            if w < 1e-4:
                continue
            raw.setdefault(vi, {})[bone] = max(raw.get(vi, {}).get(bone, 0.0), w)
            touched += 1
        blend_targets.append(bone)
        blend_stats.append({
            "part": part,
            "bone": bone,
            "cut_vertices": len(cut),
            "blended_vertices": touched,
            "radius_m": float(radius),
        })
        log(f"身体渐变 {part:20s} 切口 {len(cut):3d} 点，"
            f"影响 {touched:5d} 顶点，半径 {float(radius) * 100:g} cm")

    body.vertex_groups.clear()
    vg_body = body.vertex_groups.new(name=body_bone)
    vg_other = {bone: body.vertex_groups.new(name=bone) for bone in sorted(set(blend_targets))}
    plain = []
    for vi in range(len(body_pts)):
        ws = raw.get(vi)
        if not ws:
            plain.append(vi)
            continue
        total = sum(ws.values())
        if total > 1.0:
            ws = {b: w / total for b, w in ws.items()}
            total = 1.0
        for bone, w in ws.items():
            vg_other[bone].add([vi], float(w), "REPLACE")
        rest = 1.0 - total
        if rest > 1e-6:
            vg_body.add([vi], float(rest), "REPLACE")
    if plain:
        vg_body.add(plain, 1.0, "REPLACE")
    log(f"身体权重：{len(plain)} 顶点纯 {body_bone}，{len(raw)} 顶点带渐变")

    # 骨架显示设置；保持 rest 姿势
    arm.data.pose_position = "POSE"
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()

    # ---------- 清单 ----------
    bones_info = []
    for b in arm_data.bones:
        bones_info.append({
            "name": b.name,
            "parent": b.parent.name if b.parent else None,
            "head": [round(float(x), 5) for x in b.head_local],
            "tail": [round(float(x), 5) for x in b.tail_local],
            "connected": bool(b.use_connect),
            "deform": bool(b.use_deform),
        })

    manifest_parts = {
        body_part: {
            "bone": body_bone,
            "mode": "rigid",
            "blend_targets": sorted(set(blend_targets)),
        }
    }
    for part in [e["part"] for e in rigid_cfg]:
        entry = dict(rigid_info[part])
        entry["bones"] = [entry.pop("bone")]
        entry["mode"] = "rigid"
        manifest_parts[part] = entry
    for part in [w["part"] for w in whisker_cfg]:
        entry = dict(whisker_info[part])
        entry["mode"] = "smooth"
        manifest_parts[part] = entry

    triangles = 0
    for name in names:
        me = parts[name].data
        me.calc_loop_triangles()
        triangles += len(me.loop_triangles)

    manifest = {
        "version": 1,
        "schema": "ai3d.rig.manifest.v1",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "blender": bpy.app.version_string,
        "source_blend": source_blend,
        "config": str(rig_path),
        "project": pdir.name,
        "rig_name": rig_name,
        "rig_type": cfg.get("rig_type", "part_level_v1"),
        "file_stem": cfg.get("file_stem", f"{pdir.name}_rig"),
        "units": cfg.get("units", "m"),
        "notes": cfg.get("notes", []),
        "bones": bones_info,
        "parts": manifest_parts,
        "body_blend": blend_stats,
        "preview": cfg.get("preview", {}),
        "verify": cfg.get("verify", {}),
        "counts": {"bones": len(bones_info), "meshes": len(names),
                   "triangles": triangles},
    }
    manifest_path = out / "rig_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"已写 {manifest_path}")

    stem = manifest["file_stem"]
    blend_path = out / f"{stem}.blend"
    if save:
        # 不生成 .blend1 备份：流水线每次重建都会覆盖，留着只会多占 45 MB。
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
        log(f"已保存 {blend_path}（{blend_path.stat().st_size / 1e6:.1f} MB）")

    glb_path = out / "glb" / f"{stem}.glb"
    if export:
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.object.select_all(action="DESELECT")
        for name in names:
            parts[name].select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.gltf(
            filepath=str(glb_path),
            export_format="GLB",
            use_selection=True,
            export_apply=False,
            export_animations=False,
            export_skins=True,
            export_yup=True,
        )
        log(f"导出 {glb_path}（{glb_path.stat().st_size / 1e6:.1f} MB）")

    summary = {
        "ok": True,
        "project": pdir.name,
        "config": str(rig_path),
        "rig_blend": str(blend_path) if save else None,
        "manifest": str(manifest_path),
        "glb": str(glb_path) if export else None,
        "blend_bytes": blend_path.stat().st_size if save else None,
        "glb_bytes": glb_path.stat().st_size if export else None,
        "bones": len(bones_info),
        "meshes": len(names),
        "blend_stats": blend_stats,
    }
    log(f"[OK] 骨架与绑定完成：{len(bones_info)} 根骨 / {len(names)} 个网格")
    return summary


def main() -> None:
    args = parse_args()
    run(config_path=args.config, out_dir=args.out,
        export=not args.no_export, save=not args.no_save)


if __name__ == "__main__":
    main()
