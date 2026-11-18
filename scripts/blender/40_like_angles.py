"""阶段 40：三角度展示图（左 3/4、主视角、近侧面），输出 1200×1200 PNG。

环境变量：
  AI3D_PROJECT   项目名（必填）
  AI3D_ANGLE_RES 边长，默认 1200
  AI3D_ANGLE_SAMPLES 采样数，默认 48
"""

import importlib.util
import os

import bpy

import _common as C

ANGLES = [(-32.0, "front_left"), (24.0, "hero"), (78.0, "side")]


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> None:
    here = os.environ.get("AI3D_SCRIPT_DIR", os.path.expanduser("~/ai3d/scripts/blender"))
    cam_mod = _load("like_camera", os.path.join(here, "37_like_camera.py"))

    res = int(os.environ.get("AI3D_ANGLE_RES", "1200"))
    samples = int(os.environ.get("AI3D_ANGLE_SAMPLES", "48"))

    scene = bpy.context.scene
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.cycles.adaptive_threshold = 0.02
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"

    outdir = C.project_dir() / "angles"
    outdir.mkdir(parents=True, exist_ok=True)

    written = []
    for azim, label in ANGLES:
        os.environ["AI3D_LIKE_AZIM"] = str(azim)
        cam_mod.run()
        path = outdir / f"like86_{label}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        written.append(str(path))
        C.log(f"[OK] 角度 {label}（方位 {azim:.0f}°）→ {path}")

    C.record_stage("angles", {"files": written, "res": res, "samples": samples})


if __name__ == "__main__":
    run()
    C.save_blend()
