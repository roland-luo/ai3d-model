"""阶段 10：导入 GLB → 合并 → 归一化到 0.35m → 底面落地。"""

import _common as C


def run() -> None:
    C.log(f"项目 {C.PROJECT}：导入 GLB")
    # 全新场景才清默认立方体/灯/相机；已有 AI3D 模型时只重建 AI3D 集合
    if not C.has_mesh():
        for name in ("Cube", "Light", "Camera"):
            obj = C.bpy.data.objects.get(name)
            if obj is not None:
                C.bpy.data.objects.remove(obj, do_unlink=True)
    obj = C.import_glb()
    C.normalize(obj, C.TARGET_SIZE)
    obj["ai3d_normalized"] = True
    C.log(f"[OK] 导入完成：{C.mesh_stats(obj)}")
