"""通过环境变量分发到各个阶段。

Blender MCP 里的固定调用方式：
    import os
    os.environ["AI3D_PROJECT"] = "dragon01"
    os.environ["AI3D_STAGE"] = "rig"
    exec(open("/home/roland/ai3d/scripts/blender/run_stage.py").read())

阶段顺序：import → clean → materials → decals(可选) → studio → render
骨架支线：rig → rig-pose → rig-verify（或 rig-pose / rig-verify 单独跑）

骨架相关环境变量：
    AI3D_RIG_CONFIG    默认 <project>/rig.json
    AI3D_RIG_OUT       默认 <project>/rig
    AI3D_RIG_RES       预览边长，默认 1400
    AI3D_RIG_PREVIEW   默认 <rig>/preview
    AI3D_RIG_REPORT    验收报告，默认 <rig>/verify_report.json
"""

import bpy  # noqa: F401  （只在 Blender 里运行）

import importlib.util
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(os.environ.get("AI3D_SCRIPT_DIR", str(Path.home() / "ai3d/scripts/blender"))).resolve()
sys.path.insert(0, str(HERE))

RIG_STAGES = {"rig", "rig-pose", "rig-verify", "32", "bind", "pose", "verify"}
_RAW_STAGE = os.environ.get("AI3D_STAGE", "import").strip().lower()

# 在 MCP 里直接跑骨架阶段时，从当前 .blend 路径推断项目名，
# 省得每次都手动设 AI3D_PROJECT。
if _RAW_STAGE in RIG_STAGES and "AI3D_PROJECT" not in os.environ and bpy.data.filepath:
    _parts = Path(bpy.data.filepath).resolve().parts
    if "projects" in _parts:
        _i = _parts.index("projects")
        if _i + 1 < len(_parts):
            os.environ["AI3D_PROJECT"] = _parts[_i + 1]

# Blender 进程会缓存上次导入的 _common；每次调用强制重新加载，避免改脚本后不生效
sys.modules.pop("_common", None)
import _common as C  # noqa: E402

STAGE_FILES = {
    "import": "10_import.py",
    "clean": "20_clean.py",
    "materials": "30_materials.py",
    "decals": "40_decals.py",
    "studio": "50_studio.py",
    "render": "60_render.py",
    "rig": "32_rig_parts.py",
}
ALIASES = {
    "10": "import", "20": "clean", "30": "materials",
    "40": "decals", "50": "studio", "60": "render",
    "mat": "materials", "light": "studio",
    "32": "rig", "bind": "rig",
    "pose": "rig-pose", "verify": "rig-verify",
}


def load(stage: str):
    path = HERE / STAGE_FILES[stage]
    spec = importlib.util.spec_from_file_location(f"ai3d_stage_{stage}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# 骨架支线
# --------------------------------------------------------------------------- #
def rig_paths() -> tuple[Path, dict, Path]:
    """返回 (rig.json, 配置, 输出目录)。"""
    raw = os.environ.get("AI3D_RIG_CONFIG")
    cfg_path = (Path(raw).expanduser().resolve() if raw
                else C.project_dir() / "rig.json")
    if not cfg_path.is_file():
        raise SystemExit(
            f"[×] 找不到骨架配置 {cfg_path}\n"
            "    设置 AI3D_RIG_CONFIG，或参考 projects/dragon01/rig.json 写一份")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"[×] {cfg_path} 第 {e.lineno} 行 JSON 语法错误：{e.msg}")
    raw_out = os.environ.get("AI3D_RIG_OUT")
    out = (Path(raw_out).expanduser().resolve() if raw_out
           else cfg_path.parent / "rig")
    return cfg_path, cfg, out


def run_rig_build() -> None:
    cfg_path, _cfg, out = rig_paths()
    log = C.log
    log(f"===== {C.PROJECT} / rig =====")
    mod = load("rig")
    summary = mod.run(config_path=str(cfg_path), out_dir=str(out))
    C.record_stage("rig", {"rig": summary})
    log("[OK] 阶段 rig 完成")
    if summary.get("glb"):
        log(f"GLB：{summary['glb']}")
    log("下一步可跑 AI3D_STAGE=rig-pose 出预览，或 AI3D_STAGE=rig-verify 复检")


def run_rig_subprocess(stage: str) -> None:
    cfg_path, cfg, out = rig_paths()
    stem = cfg.get("file_stem") or f"{C.PROJECT}_rig"
    blend = out / f"{stem}.blend"
    manifest = out / "rig_manifest.json"
    glb = out / "glb" / f"{stem}.glb"
    preview = Path(os.environ.get("AI3D_RIG_PREVIEW",
                                  str(out / "preview"))).expanduser().resolve()
    report = Path(os.environ.get("AI3D_RIG_REPORT",
                                 str(out / "verify_report.json"))).expanduser().resolve()
    res = os.environ.get("AI3D_RIG_RES", "1400")
    blender = bpy.app.binary_path

    if stage == "rig-pose":
        if not blend.is_file():
            raise SystemExit(f"[×] 找不到 {blend}；先跑 AI3D_STAGE=rig")
        cmd = [blender, "-b", str(blend),
               "--python", str(HERE / "33_rig_pose.py"), "--",
               "--manifest", str(manifest), "--out", str(preview), "--res", str(res)]
        extra = {"blend": str(blend), "preview": str(preview)}
    else:
        if not glb.is_file():
            raise SystemExit(f"[×] 找不到 {glb}；先跑 AI3D_STAGE=rig")
        cmd = [blender, "-b", "--python", str(HERE / "35_verify_rig_glb.py"), "--",
               "--glb", str(glb), "--manifest", str(manifest),
               "--report", str(report)]
        extra = {"glb": str(glb), "report": str(report)}

    C.log(f"===== {C.PROJECT} / {stage} =====")
    C.log("$ " + " ".join(cmd))
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        raise SystemExit(f"[×] 阶段 {stage} 失败（退出码 {rc}）")
    C.record_stage(stage, extra)
    C.log(f"[OK] 阶段 {stage} 完成")


def main() -> None:
    stage = _RAW_STAGE
    stage = ALIASES.get(stage, stage)

    if stage == "rig":
        run_rig_build()
        return
    if stage in {"rig-pose", "rig-verify"}:
        run_rig_subprocess(stage)
        return

    if stage not in STAGE_FILES:
        raise SystemExit(f"[×] 未知阶段 {stage}，可选：{', '.join(STAGE_FILES)}")
    C.log(f"===== {C.PROJECT} / {stage} =====")

    # 前置步骤：没模型先导入；要打灯/渲染但没相机，先建棚
    if stage != "import" and not C.has_mesh():
        C.log("没有模型，先执行 import")
        load("import").run()
    if stage == "render" and C.bpy.context.scene.camera is None:
        C.log("没有相机，先执行 studio")
        load("studio").run()

    load(stage).run()

    extra = {}
    scene = C.bpy.context.scene
    if stage == "studio":
        extra = {
            "camera": scene.camera.name if scene.camera else None,
            "lights": [o.name for o in scene.objects if o.type == "LIGHT"],
        }
    elif stage == "render":
        extra = {
            "render": {
                "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                "samples": scene.cycles.samples,
                "adaptive": scene.cycles.adaptive_threshold,
                "filepath": scene.render.filepath,
                "engine": scene.render.engine,
            }
        }
    C.record_stage(stage, extra)

    if os.environ.get("AI3D_NO_SAVE") != "1":
        C.save_blend()
    C.log(f"[OK] 阶段 {stage} 完成")


# 通过 MCP 的 exec(open(...).read()) 调用时 __name__ 不一定是 __main__，
# 所以这里无条件执行入口，而不是用 if __name__ == "__main__" 保护。
try:
    main()
except Exception:
    traceback.print_exc()
    print("[×] 阶段失败，见上面的 traceback", flush=True)
    raise
