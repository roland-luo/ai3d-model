"""阶段 60：4K 渲染参数。真正的渲染交给 render_final.sh（命令行，不怕 MCP 超时）。"""

import os

import bpy

import _common as C


def run() -> None:
    scene = bpy.context.scene
    if scene.camera is None:
        raise RuntimeError("场景里没有相机，先跑 studio")
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 128
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.01
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 12
    scene.render.resolution_x = 3840
    scene.render.resolution_y = 2160
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "16"
    scene.render.image_settings.compression = 15
    scene.render.filepath = str(C.render_path())
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    C.log(f"[OK] 4K 渲染参数就绪：3840×2160 / 128 samples / {C.render_path()}")

    if os.environ.get("AI3D_RENDER_PREVIEW") == "1":
        scene.render.resolution_x = 1600
        scene.render.resolution_y = 900
        scene.cycles.samples = 32
        scene.cycles.adaptive_threshold = 0.03
        preview = C.AI3D / "renders" / f"{C.PROJECT}_preview.png"
        scene.render.filepath = str(preview)
        C.log("开始渲预览（会阻塞当前会话）...")
        bpy.ops.render.render(write_still=True)
        C.log(f"[OK] 预览已写出 {preview}")
        # 恢复 4K 参数，方便随后直接 CLI 渲染
        scene.render.resolution_x = 3840
        scene.render.resolution_y = 2160
        scene.cycles.samples = 128
        scene.cycles.adaptive_threshold = 0.01
        scene.render.filepath = str(C.render_path())
