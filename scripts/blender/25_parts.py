"""AI3D 25_parts.py — 把一整块网格拆成可独立调整的部件。

设计原则
--------
1. 不重网格化。重网格化只改面片排布，不能把粘在一起的身体/角/须分开。
2. 分件靠“种子 + 半径”在表面生长（测地线），或者用一根“胶囊”圈住细长
   的龙须。没被任何部件认领的面，归到 fallback 部件（通常是身体）。
3. 每个部件单独补洞、可选加厚、居中设原点，导出独立 GLB；同时导出
   一个保持原位置的组合 GLB。源网格保留并隐藏，绝不覆盖。

用法（推荐，独立跑，不污染源文件）
--------------------------------
    ~/.local/bin/blender -b /home/roland/ai3d/blend/dragon01.blend \
      --python /home/roland/ai3d/scripts/blender/25_parts.py -- \
      --config /home/roland/ai3d/projects/dragon01/parts.json

只查看候选种子（最远点采样）：
    ... 25_parts.py -- --config ... --print-fps 32

配置格式见 projects/dragon01/parts.json 与 README。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import _common as C  # noqa: E402
except Exception:  # 允许脱离流水线单独运行
    C = None


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    print(f"[AI3D parts] {msg}", flush=True)


def die(msg: str) -> None:
    raise SystemExit(f"[×] {msg}")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description="AI3D 网格分件")
    ap.add_argument("--config", default=os.environ.get("AI3D_PARTS_CONFIG"))
    ap.add_argument("--out", default=None, help="输出目录（默认 <project>/parts）")
    ap.add_argument("--blend", default=None, help="可选：先打开这个 .blend")
    ap.add_argument("--print-fps", type=int, default=0, metavar="N",
                    help="只打印 N 个最远点采样坐标后退出，用来挑种子")
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="只计算分件和统计，不创建对象、不写文件")
    return ap.parse_args(argv)


def project_dir(config_path: Path | None = None) -> Path:
    """项目目录以“配置文件所在目录”或“blend 文件名”为准。

    不能依赖 _common.PROJECT：它默认是 helmet01，会把 dragon01 的产物
    悄悄写到 helmet01/parts 里。显式设置 AI3D_PROJECT 时优先用它。
    """
    env = os.environ.get("AI3D_PROJECT")
    if env:
        return Path.home() / "ai3d" / "projects" / env
    if config_path is not None:
        cp = Path(config_path).resolve()
        # .../projects/dragon01/parts.json -> .../projects/dragon01
        if cp.parent.parent.name == "projects":
            return cp.parent
        return cp.parent
    if bpy.data.filepath:
        stem = Path(bpy.data.filepath).stem
        return Path.home() / "ai3d" / "projects" / stem
    return Path.cwd()


def resolve_config(path_arg: str | None) -> Path:
    if path_arg:
        p = Path(path_arg).expanduser().resolve()
        if not p.is_file():
            die(f"找不到配置文件：{p}")
        return p
    p = project_dir() / "parts.json"
    if p.is_file():
        return p
    die(
        "没有指定 --config，且默认位置不存在：\n"
        f"  {p}\n"
        "请复制一份 parts.json 到项目目录，或在命令行加 --config。"
    )
    raise AssertionError


def load_config(path: Path) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"配置文件不是合法 JSON：{path}\n{e}")
    if "parts" not in cfg or not isinstance(cfg["parts"], list):
        die("配置里必须有 parts 数组")
    for p in cfg["parts"]:
        if not p.get("id"):
            die("每个 part 都必须有 id")
        if p.get("fallback") and (p.get("seeds") or p.get("capsule")):
            die(f"{p['id']} 是 fallback，不能再写 seeds/capsule")
    ids = [p.get("id") for p in cfg["parts"]]
    if len(ids) != len(set(ids)):
        die(f"parts 里有重复 id：{ids}")
    fallbacks = [p for p in cfg["parts"] if p.get("fallback")]
    if len(fallbacks) != 1:
        die(f"必须且只能有一个 fallback 部件，现在有 {len(fallbacks)} 个")
    return cfg


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_hex_color(s: str, default=(0.5, 0.5, 0.5)) -> tuple[float, float, float]:
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except Exception:
        return default


def collection_clear(name: str) -> None:
    coll = bpy.data.collections.get(name)
    if coll is None:
        return
    for obj in list(coll.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 0) == 0:
            try:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
            except Exception:
                pass
    bpy.data.collections.remove(coll)


def ensure_collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


# --------------------------------------------------------------------------- #
# 读入源网格
# --------------------------------------------------------------------------- #
def pick_source(cfg: dict) -> bpy.types.Object:
    name = cfg.get("source_object")
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            die(f"找不到 source_object：{name}\n当前网格对象：{[o.name for o in bpy.data.objects if o.type == 'MESH']}")
        if obj.type != "MESH":
            die(f"source_object 不是网格：{name}")
        return obj
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
    if len(meshes) == 1:
        return meshes[0]
    # 选面数最多的网格；这是最稳的默认值
    meshes.sort(key=lambda o: len(o.data.polygons), reverse=True)
    if not meshes:
        die("场景里没有网格")
    log(f"未指定 source_object，自动选面数最多的网格：{meshes[0].name}")
    return meshes[0]


def mesh_arrays(obj: bpy.types.Object):
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(obj.matrix_world, dtype=np.float64)
    wco = co.astype(np.float64) @ M[:3, :3].T + M[:3, 3]
    ev = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    return me, wco, ev


def build_adjacency(wco: np.ndarray, ev: np.ndarray):
    n = len(wco)
    adj = [[] for _ in range(n)]
    for a, b in ev:
        a = int(a)
        b = int(b)
        w = float(np.linalg.norm(wco[a] - wco[b]))
        adj[a].append((b, w))
        adj[b].append((a, w))
    return adj


def farthest_points(wco: np.ndarray, count: int) -> list[int]:
    """最远点采样：先取离质心最远的点，再每次取离已选点最远的点。"""
    if count <= 0:
        return []
    center = wco.mean(axis=0)
    first = int(np.linalg.norm(wco - center, axis=1).argmax())
    sel = [first]
    d = np.linalg.norm(wco - wco[first], axis=1)
    for _ in range(1, min(count, len(wco))):
        i = int(d.argmax())
        if i in sel:
            break
        sel.append(i)
        d = np.minimum(d, np.linalg.norm(wco - wco[i], axis=1))
    return sel


# --------------------------------------------------------------------------- #
# 分件标签
# --------------------------------------------------------------------------- #
def capsule_distance(wco: np.ndarray, points: list[list[float]]) -> np.ndarray:
    """所有顶点到折线的最短距离（米）。点不足 2 个时按球处理。"""
    pts = [np.array(p, dtype=np.float64) for p in points]
    if len(pts) == 1:
        return np.linalg.norm(wco - pts[0], axis=1)
    dmin = np.full(len(wco), np.inf, dtype=np.float64)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        denom = float(np.dot(ab, ab))
        if denom <= 1e-20:
            d = np.linalg.norm(wco - a, axis=1)
        else:
            t = np.clip(((wco - a) @ ab) / denom, 0.0, 1.0)
            proj = a[None, :] + t[:, None] * ab[None, :]
            d = np.linalg.norm(wco - proj, axis=1)
        dmin = np.minimum(dmin, d)
    return dmin


def geodesic_grow(adj, seeds: list[int], radius: float, n: int) -> np.ndarray:
    """多源 Dijkstra，返回每个顶点的测地距离；超过 radius 的保持 inf。"""
    INF = np.inf
    dist = np.full(n, INF, dtype=np.float64)
    import heapq
    heap = []
    for s in seeds:
        dist[s] = 0.0
        heapq.heappush(heap, (0.0, int(s)))
    while heap:
        dv, v = heapq.heappop(heap)
        if dv > dist[v] + 1e-12:
            continue
        if dv > radius:
            continue
        for u, w in adj[v]:
            nd = dv + w
            if nd < dist[u] - 1e-12 and nd <= radius:
                dist[u] = nd
                heapq.heappush(heap, (nd, u))
    return dist


def snap_seeds(wco: np.ndarray, points: list[list[float]], pid: str, warn_m: float = 0.01):
    out, info = [], []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 3:
            die(f"{pid} 的 seed 必须是 [x, y, z]，现在是：{p}")
        p = np.array(p, dtype=np.float64)
        d = np.linalg.norm(wco - p, axis=1)
        vi = int(d.argmin())
        out.append(vi)
        info.append({
            "target": [round(float(v), 5) for v in p],
            "vertex": vi,
            "snapped": [round(float(v), 5) for v in wco[vi]],
            "distance_mm": round(float(d[vi]) * 1000.0, 3),
        })
        if d[vi] > warn_m:
            log(f"⚠ {pid} 的种子离表面 {d[vi] * 1000:.1f} mm，可能点错了；已吸附到最近顶点")
    return out, info


def build_face_adjacency(me: bpy.types.Mesh):
    nf = len(me.polygons)
    loops = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    lt = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_total", lt)
    lstart = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", lstart)
    edge_faces = defaultdict(list)
    for f in range(nf):
        s = int(lstart[f])
        t = int(lt[f])
        vs = loops[s:s + t]
        for i in range(t):
            a = int(vs[i])
            b = int(vs[(i + 1) % t])
            edge_faces[(min(a, b), max(a, b))].append(f)
    fadj = [[] for _ in range(nf)]
    for fs in edge_faces.values():
        # 注意：AI 生成的网格常有 >2 个面共用一条边的“非流形边”。
        # 这里把所有共用边的面都连起来，否则会被误判成几千个孤岛，
        # 后面的“丢弃小碎片”就会把正常表面当垃圾删掉。
        if len(fs) < 2:
            continue
        for i in range(len(fs)):
            for j in range(i + 1, len(fs)):
                a, b = fs[i], fs[j]
                if b not in fadj[a]:
                    fadj[a].append(b)
                if a not in fadj[b]:
                    fadj[b].append(a)
    return loops, lt, lstart, fadj


def faces_from_vertices(loops, lt, lstart, nf, label):
    """面标签 = 该面顶点标签的多数票；薄片不会因为一个角被切掉就改标签。"""
    flabel = np.zeros(nf, dtype=np.int32)
    for f in range(nf):
        s = int(lstart[f])
        t = int(lt[f])
        c = Counter(label[loops[s:s + t]].tolist())
        flabel[f] = c.most_common(1)[0][0]
    return flabel


def smooth_face_labels(flabel, fadj, passes: int, protect_labels: set[int]):
    for it in range(max(0, passes)):
        new = flabel.copy()
        changed = 0
        for f in range(len(flabel)):
            if int(flabel[f]) in protect_labels or not fadj[f]:
                continue
            c = Counter(int(flabel[g]) for g in fadj[f])
            top, cnt = c.most_common(1)[0]
            need = max(2, len(fadj[f]) // 2 + 1)
            if top != flabel[f] and cnt >= need:
                new[f] = top
                changed += 1
        flabel = new
        log(f"标签平滑第 {it + 1} 轮：改动 {changed} 面")
        if changed == 0:
            break
    return flabel


def drop_small_islands(flabel: np.ndarray, fadj, pixel_config: dict):
    """把每个部件里过小的孤岛标成 -1（丢弃），并返回统计。"""
    min_faces = int(pixel_config.get("min_island_faces", 30))
    keep_ratio = float(pixel_config.get("island_keep_ratio", 0.002))
    nf = len(flabel)
    report = {}
    for lab in sorted(set(int(x) for x in flabel.tolist()) - {-1}):
        fs = np.where(flabel == lab)[0]
        if len(fs) == 0:
            continue
        fs_set = set(int(x) for x in fs)
        seen = set()
        comps = []
        for f in fs:
            f = int(f)
            if f in seen:
                continue
            stack = [f]
            seen.add(f)
            comp = []
            while stack:
                g = stack.pop()
                comp.append(g)
                for h in fadj[g]:
                    if h in fs_set and h not in seen:
                        seen.add(h)
                        stack.append(h)
            comps.append(comp)
        comps.sort(key=len, reverse=True)
        if not comps:
            continue
        keep_min = max(min_faces, int(len(comps[0]) * keep_ratio))
        dropped = 0
        for comp in comps[1:]:
            if len(comp) < keep_min:
                flabel[comp] = -1
                dropped += len(comp)
        report[lab] = {
            "islands": len(comps),
            "largest": len(comps[0]),
            "second": len(comps[1]) if len(comps) > 1 else 0,
            "kept_islands": [len(c) for c in comps if len(c) >= keep_min][:8],
            "dropped_faces": dropped,
        }
    return flabel, report


def assign_parts(cfg: dict, wco: np.ndarray, adj, n: int):
    parts = cfg["parts"]
    label = np.zeros(n, dtype=np.int32)
    best = np.full(n, np.inf, dtype=np.float64)
    cap_best = np.full(n, np.inf, dtype=np.float64)
    seed_report = {}
    protect = set()

    # 1) 胶囊优先：细长、容易和身体粘住的部位（龙须）
    for pi, part in enumerate(parts):
        if "capsule" not in part:
            continue
        cap = part["capsule"]
        pts = cap.get("points") or []
        r = float(cap.get("radius_m", 0.004))
        if not pts or r <= 0:
            die(f"{part['id']} 的 capsule 需要 points 和正数 radius_m")
        d = capsule_distance(wco, pts)
        norm = d / r
        hit = norm < cap_best
        hit &= d <= r
        cap_best[hit] = norm[hit]
        label[hit] = pi
        protect.add(pi)
        log(f"胶囊 {part['id']}：半径 {r * 1000:.2f} mm，命中 {int(hit.sum())} 顶点")
        seed_report[part["id"]] = {
            "mode": "capsule",
            "points": pts,
            "radius_mm": r * 1000,
            "vertices": int(hit.sum()),
        }

    # 2) 种子 + 测地线半径
    for pi, part in enumerate(parts):
        if "seeds" not in part:
            continue
        seeds = part.get("seeds") or []
        r = float(part.get("radius_m", 0))
        if not seeds or r <= 0:
            die(f"{part['id']} 需要非空 seeds 和正数 radius_m")
        vis, info = snap_seeds(wco, seeds, part["id"])
        if len(set(vis)) != len(vis):
            log(f"⚠ {part['id']} 有两个种子吸附到同一个顶点，会自动合并")
        dist = geodesic_grow(adj, sorted(set(vis)), r, n)
        norm = dist / r
        hit = norm < best
        hit &= dist <= r
        hit &= cap_best == np.inf
        best[hit] = norm[hit]
        label[hit] = pi
        seed_report[part["id"]] = {
            "mode": "geodesic",
            "radius_mm": r * 1000,
            "seeds": info,
            "vertices": int((dist < np.inf).sum()),
        }
        log(f"生长 {part['id']}：半径 {r * 100:.0f} cm，覆盖 {int((dist < np.inf).sum())} 顶点")

    # 细长/薄片部件可以在配置里加 "protect": true，标签平滑时不动它
    for pi, part in enumerate(parts):
        if part.get("protect"):
            protect.add(pi)

    return label, seed_report, protect


# --------------------------------------------------------------------------- #
# 造物件
# --------------------------------------------------------------------------- #
def object_bounds(obj: bpy.types.Object):
    vs = obj.data.vertices
    if not vs:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    xs = [v.co.x for v in vs]
    ys = [v.co.y for v in vs]
    zs = [v.co.z for v in vs]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def create_part_object(src, face_indices, part, coll, root):
    me = src.data
    keep = set(int(i) for i in face_indices)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    del_faces = [f for f in bm.faces if f.index not in keep]
    if del_faces:
        bmesh.ops.delete(bm, geom=del_faces, context="FACES")
    bm.verts.ensure_lookup_table()
    loose_v = [v for v in bm.verts if not v.link_faces]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")
    bm.edges.ensure_lookup_table()
    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context="EDGES")

    # 补洞：切割面 + 源网格本来就有的小洞
    boundary_before = 0
    if part.get("fill_holes", cfg_global.get("fill_holes", True)):
        boundary_before = sum(1 for e in bm.edges if len(e.link_faces) == 1)
        edges = [e for e in bm.edges if len(e.link_faces) == 1]
        if edges:
            try:
                bmesh.ops.holes_fill(bm, edges=edges, sides=0)
            except Exception as e:
                log(f"⚠ {part['id']} 补洞失败：{e}")
    try:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    except Exception:
        pass

    new_me = bpy.data.meshes.new(f"{part['id']}_Mesh")
    bm.to_mesh(new_me)
    bm.free()
    new_me.update()

    # 保留源材质槽和面的 material_index
    for mat in me.materials:
        new_me.materials.append(mat)

    obj = bpy.data.objects.new(part["id"], new_me)
    coll.objects.link(obj)
    obj.matrix_world = src.matrix_world.copy()
    # 把世界变换烘进网格，再把原点放到部件包围盒中心
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    lo, hi = object_bounds(obj)
    ctr = (lo + hi) * 0.5
    obj.data.transform(Matrix.Translation(-ctr))
    obj.location = ctr
    obj.data.update()

    obj.parent = root
    obj.matrix_parent_inverse = root.matrix_world.inverted()
    obj["ai3d_part"] = part["id"]
    obj["ai3d_label_zh"] = part.get("label_zh", part["id"])
    obj["ai3d_source"] = src.name
    obj.color = (*parse_hex_color(part.get("color", "#808080")), 1.0)

    for p in new_me.polygons:
        p.use_smooth = bool(part.get("shade_smooth", cfg_global.get("shade_smooth", True)))

    # 可选加厚
    thick_mm = float(part.get("solidify_mm", 0) or 0)
    if thick_mm > 0:
        try:
            mod = obj.modifiers.new("Solidify", "SOLIDIFY")
            mod.thickness = thick_mm / 1000.0
            mod.offset = -1.0
            mod.use_rim = True
            mod.use_quality_normals = True
            with bpy.context.temp_override(active_object=obj, object=obj,
                                           selected_objects=[obj],
                                           selected_editable_objects=[obj]):
                bpy.ops.object.modifier_apply(modifier=mod.name)
            log(f"{part['id']} 加厚 {thick_mm:.2f} mm")
        except Exception as e:
            log(f"⚠ {part['id']} 加厚失败（已跳过）：{e}")
            if obj.modifiers.get("Solidify"):
                obj.modifiers.remove(obj.modifiers["Solidify"])

    return obj, boundary_before


def qa_object(obj: bpy.types.Object) -> dict:
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold_e = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    nonmanifold_v = sum(1 for v in bm.verts if v.link_faces and not v.is_manifold)
    loose_v = sum(1 for v in bm.verts if not v.link_faces)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    try:
        volume = abs(bm.calc_volume(signed=True))
    except Exception:
        volume = None
    # 连通块（用面对象本身做集合，避免 bmesh 索引未更新导致误判）
    seen = set()
    islands = 0
    for f in bm.faces:
        if f in seen:
            continue
        islands += 1
        stack = [f]
        seen.add(f)
        while stack:
            g = stack.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
    bm.free()
    me.calc_loop_triangles()
    return {
        "verts": len(me.vertices),
        "faces": len(me.polygons),
        "tris": len(me.loop_triangles),
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold_e,
        "nonmanifold_verts": nonmanifold_v,
        "loose_verts": loose_v,
        "loose_edges": loose_e,
        "islands": islands,
        "watertight": boundary == 0 and nonmanifold_e == 0 and loose_v == 0,
        "volume_m3": round(volume, 10) if volume is not None else None,
        "uv_layers": [uv.name for uv in me.uv_layers],
        "materials": [m.name for m in me.materials if m],
        "dimensions_m": [round(float(v), 5) for v in obj.dimensions],
        "location_m": [round(float(v), 5) for v in obj.location],
    }


# --------------------------------------------------------------------------- #
# 导出
# --------------------------------------------------------------------------- #
def select_only(objs):
    for o in bpy.context.view_layer.objects:
        try:
            o.select_set(False)
        except Exception:
            pass
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def export_glb(path: Path, objs):
    select_only(objs)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_normals=True,
        export_texcoords=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
cfg_global: dict = {}


def main() -> None:
    global cfg_global
    args = parse_args()

    if args.blend:
        p = Path(args.blend).expanduser().resolve()
        if not p.is_file():
            die(f"找不到 blend：{p}")
        bpy.ops.wm.open_mainfile(filepath=str(p))

    config_path = resolve_config(args.config)
    cfg = load_config(config_path)
    cfg_global = cfg
    pdir = project_dir(config_path)
    if args.out:
        out_dir = Path(args.out).expanduser().resolve()
    elif cfg.get("out_dir"):
        out_dir = Path(cfg["out_dir"]).expanduser()
        if not out_dir.is_absolute():
            out_dir = pdir / out_dir
        out_dir = out_dir.resolve()
    else:
        out_dir = (pdir / "parts").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    source_blend = bpy.data.filepath
    project_name = Path(source_blend).stem or "model"
    src = pick_source(cfg)
    me, wco, ev = mesh_arrays(src)
    n = len(wco)
    if n == 0 or len(me.polygons) == 0:
        die("源网格是空的")
    log(f"源对象 {src.name}：{n:,} 顶点 / {len(me.polygons):,} 面 / 材质 {[m.name for m in me.materials if m]}")
    lo = wco.min(axis=0)
    hi = wco.max(axis=0)
    log(f"包围盒 min={np.round(lo, 4).tolist()} max={np.round(hi, 4).tolist()}")

    if args.print_fps:
        sel = farthest_points(wco, args.print_fps)
        fps = [{"i": i, "p": [round(float(x), 5) for x in wco[i]]} for i in sel]
        print("FPS_POINTS")
        for f in fps:
            print(f"  {f['i']:6d}  {f['p']}")
        (out_dir / "fps_points.json").write_text(json.dumps(fps, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"已写 {out_dir / 'fps_points.json'}")
        return

    t0 = time.time()
    adj = build_adjacency(wco, ev)
    label, seed_report, protect = assign_parts(cfg, wco, adj, n)
    loops, lt, lstart, fadj = build_face_adjacency(me)
    flabel = faces_from_vertices(loops, lt, lstart, len(me.polygons), label)
    flabel = smooth_face_labels(flabel, fadj, int(cfg.get("smoothing_passes", 3)), protect)
    flabel, island_report = drop_small_islands(flabel, fadj, cfg)
    log(f"分件计算完成，用时 {time.time() - t0:.1f}s")

    # 每个部件的面数
    counts = Counter(int(x) for x in flabel.tolist())
    for pi, part in enumerate(cfg["parts"]):
        log(f"  {part['id']:18s} {counts.get(pi, 0):7,d} 面")
    if counts.get(-1, 0):
        log(f"  丢弃的小碎片：{counts[-1]:,} 面")

    if args.dry_run:
        log("dry-run：不创建对象、不写 blend/GLB")
        return

    # 清理旧部件集合
    coll_name = cfg.get("collection", f"{Path(bpy.data.filepath).stem}_Parts")
    collection_clear(coll_name)
    coll = ensure_collection(coll_name)
    root = bpy.data.objects.new(cfg.get("root_name", f"{coll_name}_Root"), None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.05
    coll.objects.link(root)

    parts_out = []
    skipped = []
    for pi, part in enumerate(cfg["parts"]):
        fs = np.where(flabel == pi)[0]
        if len(fs) == 0:
            log(f"⚠ {part['id']} 没有分到面，跳过")
            skipped.append(part["id"])
            continue
        obj, boundary_before = create_part_object(src, fs, part, coll, root)
        qa = qa_object(obj)
        qa["id"] = part["id"]
        qa["label_zh"] = part.get("label_zh", part["id"])
        qa["boundary_before_fill"] = boundary_before
        qa["island_report"] = island_report.get(pi, {})
        parts_out.append({"obj": obj, "cfg": part, "qa": qa})
        log(
            f"建立 {part['id']:18s} 面 {qa['faces']:7,d}  边界 {qa['boundary_edges']:4d}  "
            f"非流形边 {qa['nonmanifold_edges']:5d}  孤岛 {qa['islands']:2d}"
        )

    if not parts_out:
        die("没有生成任何部件，检查 seeds/radius 或 fallback")

    # 隐藏源对象（只在当前 parts 场景里隐藏，源文件不保存）
    try:
        src.hide_render = True
        src.hide_set(True)
        src.hide_viewport = True
    except Exception:
        pass

    parts_blend = out_dir / f"{project_name}_parts.blend"
    if not args.no_save:
        bpy.ops.wm.save_as_mainfile(filepath=str(parts_blend), check_existing=False)
        log(f"已保存 {parts_blend}")

    manifest = {
        "version": 1,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "blender": bpy.app.version_string,
        "config": str(config_path),
        "source_blend": source_blend,
        "source_object": src.name,
        "source_stats": {
            "verts": n,
            "faces": len(me.polygons),
            "bbox_min": [round(float(x), 5) for x in lo],
            "bbox_max": [round(float(x), 5) for x in hi],
            "materials": [m.name for m in me.materials if m],
        },
        "seeds": seed_report,
        "islands": {cfg["parts"][k]["id"]: v for k, v in island_report.items()},
        "parts": [{k: v for k, v in p["qa"].items()} for p in parts_out],
        "skipped": skipped,
    }
    (out_dir / "parts_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"已写 {out_dir / 'parts_manifest.json'}")

    if args.no_export:
        log("--no-export：跳过 GLB 导出")
        return

    glb_dir = out_dir / "glb"
    glb_dir.mkdir(parents=True, exist_ok=True)
    try:
        export_glb(glb_dir / f"{project_name}_parts.glb", [root] + [p["obj"] for p in parts_out])
        log(f"组合 GLB：{glb_dir / f'{project_name}_parts.glb'}")
    except Exception as e:
        log(f"⚠ 组合 GLB 导出失败：{e}")

    centered = bool(cfg.get("export_parts_centered", True))
    for p in parts_out:
        obj = p["obj"]
        pid = p["cfg"]["id"]
        old_parent = obj.parent
        old_loc = obj.location.copy()
        try:
            obj.parent = None
            if centered:
                obj.location = (0.0, 0.0, 0.0)
            export_glb(glb_dir / f"{pid}.glb", [obj])
            log(f"单件 GLB：{glb_dir / f'{pid}.glb'}")
        except Exception as e:
            log(f"⚠ {pid} 单件导出失败：{e}")
        finally:
            obj.parent = old_parent
            obj.location = old_loc

    log(f"[OK] 分件完成：{len(parts_out)} 件；输出 {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise SystemExit(f"[×] 分件失败：{e}")
