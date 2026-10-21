"""通过环境变量分发到各个阶段。

Blender MCP 里的固定调用方式：
    import os
    os.environ["AI3D_PROJECT"] = "helmet01"
    os.environ["AI3D_STAGE"] = "import"
    exec(open("/home/roland/ai3d/scripts/blender/run_stage.py").read())

阶段顺序：import → clean → materials → decals(可选) → studio → render
"""

import importlib.util
import os
import sys
import traceback
from pathlib import Path

HERE = Path(os.environ.get("AI3D_SCRIPT_DIR", str(Path.home() / "ai3d/scripts/blender"))).resolve()
sys.path.insert(0, str(HERE))

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
}
ALIASES = {
    "10": "import", "20": "clean", "30": "materials",
    "40": "decals", "50": "studio", "60": "render",
    "mat": "materials", "light": "studio",
}


def load(stage: str):
    path = HERE / STAGE_FILES[stage]
    spec = importlib.util.spec_from_file_location(f"ai3d_stage_{stage}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    stage = os.environ.get("AI3D_STAGE", "import").strip().lower()
    stage = ALIASES.get(stage, stage)
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
