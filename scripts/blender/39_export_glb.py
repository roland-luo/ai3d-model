"""阶段 39：把打好材质的模型导出成 GLB（带 Principled 材质与清漆层）。

环境变量：
  AI3D_PROJECT   项目名（必填）
  AI3D_EXPORT    输出文件名，默认 <project>_model.glb
"""

import os
from pathlib import Path

import bpy

import _common as C


def run() -> None:
    obj = C.model_object()
    if obj is None:
        raise RuntimeError("场景里没有 AI3D 网格")

    out = C.project_dir() / os.environ.get("AI3D_EXPORT", f"{C.PROJECT}_model.glb")

    # 导出前把物体放回地面，避免带着产品台的高度
    lift = float(obj.get("ai3d_lift", 0.0))
    if lift:
        obj.location.z -= lift
        C.log(f"[i] 下沉 {lift:.3f} m 回地面")

    # glTF 不支持把节点网络烘成 baseColorFactor：导出前把 Base Color 临时换成实色，
    # 否则在别的查看器里模型会是白色。导出后复原。
    restore = []
    hex_col = os.environ.get("AI3D_EXPORT_COLOR", "#FF5A1F").lstrip("#")
    srgb = [int(hex_col[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in srgb]
    for mat in obj.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != "BSDF_PRINCIPLED":
                continue
            inp = node.inputs["Base Color"]
            for link in list(inp.links):
                restore.append((mat, link.from_socket, inp))
                mat.node_tree.links.remove(link)
            inp.default_value = (*lin, 1.0)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )

    for mat, from_socket, inp in restore:
        mat.node_tree.links.new(from_socket, inp)

    if lift:
        obj.location.z += lift  # 场景复原，.blend 保持原来的台面高度

    size = out.stat().st_size / 1e6
    C.log(f"[OK] 导出 GLB：{out}（{size:.1f} MB，{C.tri_count(obj)} 三角面）")
    C.record_stage("export_glb", {"glb": str(out), "mb": round(size, 2)})


if __name__ == "__main__":
    run()
