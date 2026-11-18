"""AI3D 35_verify_rig_glb.py — 重新导入绑定 GLB，做机器验收（清单驱动）。

检查五件事：
1. GLB 容器里有 1 套 skin，网格数/关节数和 rig_manifest.json 一致，没有动画；
2. 每个网格都带 JOINTS_0 / WEIGHTS_0，导入后都有 Armature 修改器；
3. 每个顶点的权重和都约等于 1，没有漏权重；
4. 骨头层级和 rig_manifest.json 里记录的设计一致；
5. rig.json 的 verify.pose_tests 里定义的变形测试真的生效：
   该动的件动够，不该动的件不乱动。

换模型时不用改这个脚本：它会读 rig_manifest.json 里的骨树、件名和测试表。
每次验收会写一份 JSON 报告，供 run_rig.py 汇总。

用法：
    ~/.local/bin/blender -b --python scripts/blender/35_verify_rig_glb.py -- \
      --glb projects/dragon01/rig/glb/dragon01_rig.glb \
      --manifest projects/dragon01/rig/rig_manifest.json \
      --report projects/dragon01/rig/verify_report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import struct
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HOME = Path.home()


def log(msg: str) -> None:
    print(f"[AI3D verify] {msg}", flush=True)


def die(msg: str) -> None:
    raise SystemExit(f"[×] 验收失败：{msg}")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description="AI3D 绑定 GLB 验收")
    ap.add_argument("--glb", required=True)
    ap.add_argument("--manifest", default=None,
                    help="默认找 GLB 旁边的 ../rig_manifest.json")
    ap.add_argument("--report", default=None, help="写机器可读的 JSON 报告")
    ap.add_argument("--expect-bones", type=int, default=None)
    ap.add_argument("--expect-meshes", type=int, default=None)
    return ap.parse_args(argv)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} 不是合法 JSON：第 {e.lineno} 行 {e.msg}")


def resolve_manifest(glb: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            die(f"找不到清单：{p}")
        return p
    for p in (glb.parent.parent / "rig_manifest.json",
              glb.parent / "rig_manifest.json"):
        if p.is_file():
            return p
    die(f"找不到 rig_manifest.json；请显式传 --manifest。GLB 在 {glb}")


def read_glb_json(path: Path) -> tuple[dict, int]:
    data = path.read_bytes()
    if len(data) < 12:
        die("文件小于 12 字节，不是 GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        die("GLB magic 不对")
    if version != 2:
        die(f"要 glTF 2.0，实际 {version}")
    if length != len(data):
        die(f"GLB 头部长度 {length} 和文件大小 {len(data)} 不一致")
    off = 12
    js = None
    while off < len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, off)
        off += 8
        chunk = data[off:off + chunk_len]
        off += chunk_len
        if chunk_type == 0x4E4F534A:  # JSON
            js = json.loads(chunk.decode("utf-8"))
    if js is None:
        die("找不到 GLB 的 JSON chunk")
    return js, len(data)


def check_container(js: dict, expect_meshes: int, expect_bones: int) -> dict:
    meshes = js.get("meshes", [])
    skins = js.get("skins", [])
    anims = js.get("animations", [])
    if len(meshes) != expect_meshes:
        die(f"GLB 网格数 {len(meshes)}，期望 {expect_meshes}")
    if len(skins) != 1:
        die(f"GLB skin 数 {len(skins)}，期望 1")
    joints = skins[0].get("joints", [])
    if len(joints) != expect_bones:
        die(f"skin joint 数 {len(joints)}，期望 {expect_bones}")
    if anims:
        die(f"GLB 里不该有动画，实际 {len(anims)} 条")
    total_tris = 0
    for m in meshes:
        for p in m.get("primitives", []):
            attrs = p.get("attributes", {})
            if "JOINTS_0" not in attrs or "WEIGHTS_0" not in attrs:
                die(f"网格 {m.get('name')} 缺 JOINTS_0/WEIGHTS_0")
            if "indices" in p:
                count = js["accessors"][p["indices"]]["count"]
                total_tris += count // 3
            else:
                total_tris += js["accessors"][attrs["POSITION"]]["count"] // 3
    log(f"GLB 容器：{len(meshes)} 网格 / 1 skin / {len(joints)} joints / "
        f"0 动画 / {total_tris:,} 三角面")
    return {"meshes": len(meshes), "joints": len(joints), "tris": total_tris}


def weight_report(meshes: list[bpy.types.Object]) -> dict:
    stats = {}
    for o in meshes:
        bad_sum = 0
        no_group = 0
        for v in o.data.vertices:
            s = sum(g.weight for g in v.groups)
            if not v.groups:
                no_group += 1
            elif abs(s - 1.0) > 0.02:
                bad_sum += 1
        if no_group or bad_sum:
            die(f"{o.name} 权重异常：{no_group} 个顶点没组，{bad_sum} 个和≠1")
        stats[o.name] = {"vertices": len(o.data.vertices), "ok": True}
        log(f"权重 {o.name:20s} {len(o.data.vertices):6d} 顶点，和=1 ✓")
    return stats


def maxima(obj: bpy.types.Object) -> list[Vector]:
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    mw = ev.matrix_world
    out = [mw @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return out


def max_move(a: list[Vector], b: list[Vector]) -> float:
    if len(a) != len(b):
        die(f"顶点数在姿势前后变了：{len(a)} -> {len(b)}")
    return max(((p - q).length for p, q in zip(a, b)), default=0.0)


def reset_pose(arm: bpy.types.Object) -> None:
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def wrot(arm: bpy.types.Object, bone: str, axis: str, deg: float) -> None:
    pb = arm.pose.bones.get(bone)
    if pb is None:
        die(f"姿势测试里的骨头不存在：{bone}")
    M = pb.matrix.copy()
    h = pb.head.copy()
    R = Matrix.Rotation(math.radians(deg), 4, axis)
    pb.matrix = Matrix.Translation(h) @ R @ Matrix.Translation(-h) @ M
    bpy.context.view_layer.update()


def run(glb_path: str, manifest_path: str | None = None,
        report_path: str | None = None,
        expect_bones: int | None = None,
        expect_meshes: int | None = None) -> dict:
    glb = Path(glb_path).expanduser().resolve()
    if not glb.is_file():
        die(f"找不到 GLB：{glb}")
    manifest_file = resolve_manifest(glb, manifest_path)
    manifest = read_json(manifest_file)

    parts = list(manifest.get("parts", {}).keys())
    bones_spec = manifest.get("bones", [])
    if not parts:
        die(f"{manifest_file} 里没有 parts")
    if not bones_spec:
        die(f"{manifest_file} 里没有 bones")
    n_bones = expect_bones or len(bones_spec)
    n_meshes = expect_meshes or len(parts)
    if n_bones != len(bones_spec):
        die(f"--expect-bones={n_bones} 和清单里的 {len(bones_spec)} 不一致")
    if n_meshes != len(parts):
        die(f"--expect-meshes={n_meshes} 和清单里的 {len(parts)} 不一致")

    js, size = read_glb_json(glb)
    container = check_container(js, n_meshes, n_bones)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        die(f"导入后骨架数 {len(arms)}，期望 1")
    arm = arms[0]
    if len(arm.data.bones) != n_bones:
        die(f"骨架骨数 {len(arm.data.bones)}，期望 {n_bones}")
    expected_parent = {b["name"]: b.get("parent") for b in bones_spec}
    for name, parent in expected_parent.items():
        b = arm.data.bones.get(name)
        if b is None:
            die(f"缺骨头 {name}")
        actual = b.parent.name if b.parent else None
        if actual != parent:
            die(f"骨头 {name} 的父级是 {actual}，期望 {parent}")
    log(f"骨架 {arm.name}：{len(arm.data.bones)} 骨，层级与清单一致 ✓")

    meshes = []
    for name in parts:
        o = bpy.data.objects.get(name)
        if o is None or o.type != "MESH":
            die(f"导入后找不到网格 {name}")
        mods = [m for m in o.modifiers if m.type == "ARMATURE" and m.object == arm]
        if not mods:
            die(f"{name} 没有指向 {arm.name} 的 Armature 修改器")
        if not o.vertex_groups:
            die(f"{name} 没有顶点组")
        meshes.append(o)
    extra = [o for o in bpy.data.objects
             if o.type == "MESH" and o.name not in parts]
    if extra:
        log(f"忽略导入器附带的非交付网格：{[o.name for o in extra]}"
            "（不在 GLB meshes 内）")
    log(f"网格：{len(meshes)} 个，全部带 Armature 修改器和顶点组 ✓")
    weights = weight_report(meshes)

    tests = (manifest.get("verify") or {}).get("pose_tests", [])
    test_results = []
    if not tests:
        log("⚠ 清单里没有 verify.pose_tests，跳过变形测试（容器/层级/权重已验）")
    else:
        rest = {name: maxima(bpy.data.objects[name]) for name in parts}
        for test in tests:
            name = test.get("name", test.get("bone", "?"))
            bone = test["bone"]
            axis = test.get("axis", "Z")
            deg = float(test.get("deg", 0))
            wrot(arm, bone, axis, deg)
            posed = {part: maxima(bpy.data.objects[part]) for part in parts}
            values = {part: max_move(rest[part], posed[part]) * 1000.0 for part in parts}

            for rule in test.get("moves", []) + test.get("stays", []):
                if rule.get("part") not in values:
                    die(f"{name} 的测试规则引用了清单里没有的件：{rule.get('part')}")
            for rule in test.get("moves", []):
                part = rule["part"]
                need = float(rule.get("min_mm", 0))
                if values.get(part, 0.0) < need:
                    die(f"{name}：{part} 位移 {values.get(part, 0):.1f} mm，"
                        f"低于要求 {need:.1f} mm")
            for rule in test.get("stays", []):
                part = rule["part"]
                limit = float(rule.get("max_mm", 1e9))
                if values.get(part, 0.0) > limit:
                    die(f"{name}：{part} 动了 {values.get(part, 0):.3f} mm，"
                        f"超过允许 {limit:.3f} mm；权重可能串了")

            reported = list(dict.fromkeys(
                [r["part"] for r in test.get("moves", [])]
                + [r["part"] for r in test.get("stays", [])]
            ))
            line = " / ".join(f"{p} {values[p]:.1f} mm" for p in reported)
            log(f"{name}（{bone} {axis}{deg:+g}°）：{line} ✓")
            test_results.append({
                "name": name,
                "bone": bone,
                "axis": axis,
                "deg": deg,
                "values_mm": {p: round(values[p], 3) for p in reported},
                "ok": True,
            })
            reset_pose(arm)

    report = {
        "ok": True,
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "glb": str(glb),
        "manifest": str(manifest_file),
        "bytes": size,
        "tris": container["tris"],
        "meshes": container["meshes"],
        "bones": container["joints"],
        "skins": 1,
        "animations": 0,
        "hierarchy_ok": True,
        "weights_ok": True,
        "weight_stats": weights,
        "pose_tests": test_results,
    }
    if report_path:
        path = Path(report_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"已写验收报告 {path}")

    log(f"[OK] 绑定验收通过：{size / 1e6:.1f} MB / {container['tris']:,} 三角面 / "
        f"{len(meshes)} 网格 / {len(arm.data.bones)} 骨 / 权重和=1")
    return report


def write_failure(report_path: str | None, glb: str, error: str) -> None:
    if not report_path:
        return
    path = Path(report_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "ok": False,
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "glb": str(Path(glb).expanduser().resolve()),
        "error": error,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    try:
        run(args.glb, args.manifest, args.report,
            args.expect_bones, args.expect_meshes)
    except SystemExit as e:
        write_failure(args.report, args.glb, str(e))
        raise
    except Exception as e:
        write_failure(args.report, args.glb, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("[×] 验收脚本异常，见上面的 traceback", flush=True)
        raise
