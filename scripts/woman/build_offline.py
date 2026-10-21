#!/usr/bin/env python3
"""Bundle the woman01 viewer into one double-clickable HTML file.

Classic <script> (not ES module) so it works from file:// without a server.
Three.js, GLTFLoader, OrbitControls, BufferGeometryUtils and the three GLB
models are all inlined. Output: projects/woman01/夏风换装间.html
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

PROJECT = Path("/home/roland/ai3d/projects/woman01")
VIEWER = PROJECT / "viewer"
VENDOR = VIEWER / "vendor" / "three"
OUT = PROJECT / "夏风换装间.html"

MODELS = {
    "dress": VIEWER / "assets" / "outfit_dress.glb",
    "casual": VIEWER / "assets" / "outfit_casual.glb",
    "adventurer": VIEWER / "assets" / "outfit_adventurer.glb",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_final_export(source: str, replacement: str) -> str:
    match = re.search(r"^export\s*\{(.*?)\};", source, re.M | re.S)
    if not match:
        raise SystemExit("final export block not found")
    return source[: match.start()] + replacement + source[match.end():]


def bundle_three() -> str:
    source = read(VENDOR / "three.module.js")
    match = re.search(r"^export\s*\{(.*?)\};", source, re.M | re.S)
    if not match:
        raise SystemExit("three: export block not found")
    names = match.group(1)
    body = source[: match.start()] + f"window.THREE = {{{names}}};\n" + source[match.end():]
    if re.search(r"^\s*(import|export)\b", body, re.M):
        raise SystemExit("three: leftover ESM syntax")
    return "/* Three.js r169 — MIT — inlined */\n" + body


def bundle_buffer_geometry_utils() -> str:
    source = read(VENDOR / "addons" / "utils" / "BufferGeometryUtils.js")
    source, count = re.subn(
        r"^import\s*\{(.*?)\}\s*from\s*'three';\s*",
        r"const {\1} = window.THREE;\n",
        source,
        count=1,
        flags=re.M | re.S,
    )
    if count != 1:
        raise SystemExit("BufferGeometryUtils: import block not found")
    match = re.search(r"^export\s*\{(.*?)\};", source, re.M | re.S)
    if not match:
        raise SystemExit("BufferGeometryUtils: export block not found")
    names = match.group(1)
    body = source[: match.start()] + source[match.end():]
    body = re.sub(r"^export\s+(function|class|const|let|var)\s+", r"\1 ", body, flags=re.M)
    if re.search(r"^\s*(import|export)\b", body, re.M):
        raise SystemExit("BufferGeometryUtils: leftover ESM syntax")
    return (
        "/* three/addons BufferGeometryUtils — MIT — inlined */\n"
        "window.BufferGeometryUtils = (function(){\n'use strict';\n"
        + body
        + f"\nreturn {{{names}}};\n}})();\n"
    )


def bundle_gltf_loader() -> str:
    source = read(VENDOR / "addons" / "loaders" / "GLTFLoader.js")
    source, count = re.subn(
        r"^import\s*\{(.*?)\}\s*from\s*'three';\s*",
        r"const {\1} = window.THREE;\n",
        source,
        count=1,
        flags=re.M | re.S,
    )
    if count != 1:
        raise SystemExit("GLTFLoader: three import not found")
    source, count = re.subn(
        r"^import\s*\{\s*toTrianglesDrawMode\s*\}\s*from\s*'[^']*BufferGeometryUtils\.js';\s*",
        "const { toTrianglesDrawMode } = window.BufferGeometryUtils;\n",
        source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise SystemExit("GLTFLoader: BufferGeometryUtils import not found")
    match = re.search(r"^export\s*\{\s*GLTFLoader\s*\};", source, re.M)
    if not match:
        raise SystemExit("GLTFLoader: export not found")
    body = source[: match.start()] + source[match.end():]
    if re.search(r"^\s*(import|export)\b", body, re.M):
        raise SystemExit("GLTFLoader: leftover ESM syntax")
    return (
        "/* three/addons GLTFLoader — MIT — inlined */\n"
        "window.GLTFLoader = (function(){\n'use strict';\n"
        + body
        + "\nreturn GLTFLoader;\n})();\n"
    )


def bundle_orbit_controls() -> str:
    source = read(VENDOR / "addons" / "controls" / "OrbitControls.js")
    source, count = re.subn(
        r"^import\s*\{(.*?)\}\s*from\s*'three';\s*",
        r"const {\1} = window.THREE;\n",
        source,
        count=1,
        flags=re.M | re.S,
    )
    if count != 1:
        raise SystemExit("OrbitControls: import not found")
    match = re.search(r"^export\s*\{\s*OrbitControls\s*\};", source, re.M)
    if not match:
        raise SystemExit("OrbitControls: export not found")
    body = source[: match.start()] + source[match.end():]
    if re.search(r"^\s*(import|export)\b", body, re.M):
        raise SystemExit("OrbitControls: leftover ESM syntax")
    return (
        "/* three/addons OrbitControls — MIT — inlined */\n"
        "window.OrbitControls = (function(){\n'use strict';\n"
        + body
        + "\nreturn OrbitControls;\n})();\n"
    )


def bundle_app() -> str:
    source = read(VIEWER / "app.js")
    source = re.sub(r"^import\s+.*?;\s*$", "", source, flags=re.M)
    if re.search(r"^\s*(import|export)\b", source, re.M):
        raise SystemExit("app: leftover ESM syntax")
    return (
        "/* 夏风 · 换装间 — viewer app */\n"
        "(function(){\n'use strict';\n"
        "const THREE = window.THREE;\n"
        "const GLTFLoader = window.GLTFLoader;\n"
        "const OrbitControls = window.OrbitControls;\n"
        + source
        + "\n})();\n"
    )


def embedded_models() -> str:
    chunks = []
    for key, path in MODELS.items():
        raw = path.read_bytes()
        chunks.append(f'{key}:"{base64.b64encode(raw).decode("ascii")}"')
    return "window.EMBEDDED_MODELS = {\n" + ",\n".join(chunks) + "\n};\n"


def main() -> None:
    html = read(VIEWER / "index.html")
    html, count = re.subn(
        r'<script type="importmap">.*?</script>\s*',
        "",
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("importmap not found in index.html")

    placeholder = '<script type="module" src="./app.js"></script>'
    if placeholder not in html:
        raise SystemExit("app script tag not found in index.html")

    pieces = [
        "/* 单文件离线版：所有依赖与模型已内嵌，双击即可打开 */\n",
        embedded_models(),
        bundle_three(),
        bundle_buffer_geometry_utils(),
        bundle_gltf_loader(),
        bundle_orbit_controls(),
        bundle_app(),
    ]
    bundle = "\n".join(pieces)
    if "</script" in bundle.lower():
        raise SystemExit("bundle contains a closing script tag")
    html = html.replace(placeholder, "<script>\n" + bundle + "\n</script>")
    html = html.replace(
        "<title>夏风 · 换装间 | 可换装 3D 角色</title>",
        "<title>夏风 · 换装间 | 离线单文件版</title>",
    )
    OUT.write_text(html, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"built {OUT} ({size:,} bytes / {size / 1024 / 1024:.2f} MiB)")


if __name__ == "__main__":
    main()
