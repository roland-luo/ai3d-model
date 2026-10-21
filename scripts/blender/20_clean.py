"""阶段 20：清理网格（松散点、重合并、法线、平滑、抽面）。"""

import os

import bmesh

import _common as C

TRI_TARGET = int(os.environ.get("AI3D_TRIS", "250000"))
MERGE_DIST = float(os.environ.get("AI3D_MERGE_DIST", "0.0002"))


def remove_small_islands(bm: bmesh.types.BMesh) -> int:
    """只删真正的小碎块：包围盒对角线 < 整体 2%。避免误删悬浮的小配件。"""
    bm.faces.ensure_lookup_table()
    if not bm.verts:
        return 0
    lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
    hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
    model_diag = sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5
    min_diag = model_diag * 0.02

    seen: set[int] = set()
    comps: list[list[bmesh.types.BMFace]] = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        seen.add(f.index)
        comp = []
        while stack:
            cf = stack.pop()
            comp.append(cf)
            for e in cf.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        seen.add(nf.index)
                        stack.append(nf)
        comps.append(comp)
    if len(comps) <= 1:
        return 0

    def comp_diag(comp):
        vs = {v for f in comp for v in f.verts}
        clo = [min(v.co[i] for v in vs) for i in range(3)]
        chi = [max(v.co[i] for v in vs) for i in range(3)]
        return sum((chi[i] - clo[i]) ** 2 for i in range(3)) ** 0.5

    drop = [f for comp in comps if comp_diag(comp) < min_diag for f in comp]
    if drop:
        bmesh.ops.delete(bm, geom=drop, context="FACES")
    return len(drop)


def run() -> None:
    obj = C.model_object()
    if obj is None:
        raise RuntimeError("场景里没有 AI3D 网格，先跑 import")
    C.log(f"清理前：{C.mesh_stats(obj)}")

    # 去掉上一次留下的修改器，保证可以重复执行
    for m in list(obj.modifiers):
        if m.name.startswith("AI3D_"):
            obj.modifiers.remove(m)

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=MERGE_DIST)
    dropped = remove_small_islands(bm)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    C.log(f"重合并/去松散点/去碎块：丢掉 {dropped} 个面，剩 {len(me.polygons)} 面")

    # 抽面到目标三角面数
    tris = C.tri_count(obj)
    if tris > TRI_TARGET * 1.1:
        ratio = TRI_TARGET / tris
        mod = obj.modifiers.new("AI3D_Decimate", "DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        C.apply_modifier(obj, mod.name)
        C.log(f"抽面 {tris} → {C.tri_count(obj)}（目标 {TRI_TARGET}）")

    C.smooth_by_angle(obj, 35.0)

    wn = obj.modifiers.new("AI3D_WeightedNormal", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    wn.weight = 50
    try:
        wn.mode = "FACE_AREA"
    except Exception:
        pass

    loose = C.count_loose_verts(obj)
    if loose:
        C.log(f"[!] 还有 {loose} 个松散点")
    obj["ai3d_cleaned"] = True
    C.log(f"[OK] 清理完成：{C.mesh_stats(obj)}")
