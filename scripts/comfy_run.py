#!/usr/bin/env python3
"""AI3D —— ComfyUI 批量跑图 / 跑 3D 的命令行工具（只用标准库）。

三个子命令：
    t2i   文生图（Qwen-Image 2.1 UC）
    edit  图生图 / 清理背景（Qwen-Image 2.1 UC）
    hy3d  单图转 3D（Hunyuan3D 2.1，输出 GLB）

例子：
    python3 comfy_run.py t2i --prompt "..." --seed 42 --batch 4 \
        --outdir ~/ai3d/refs/helmet01
    python3 comfy_run.py edit --image ~/ai3d/refs/helmet01/concept_01.png \
        --prompt "turn <image1> into ..." --outdir ~/ai3d/refs/helmet01 --name hy_input.png
    python3 comfy_run.py hy3d --image ~/ai3d/refs/helmet01/hy_input.png \
        --outdir ~/ai3d/projects/helmet01 --name model.glb

设计要点：
- 工作流 JSON 里只按 class_type 找节点，不依赖节点 ID；官方模板改了 ID 也不怕。
- 图片先 POST /upload/image，再提交 /prompt，轮询 /history，最后 /view 取回文件。
- 失败自动重试 2 次（共 3 次尝试）；结束时 /free 卸载模型，给下一环节腾显存。
- 每次运行写一份 run_<mode>_<时间>.json，记录 prompt/seed/模型/耗时/prompt_id/文件校验。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HOME = Path.home()
DEFAULT_API = HOME / "ai3d/workflows/api"
SERVER_DEFAULT = "http://127.0.0.1:8188"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def http_json(url: str, payload: dict | None = None, timeout: int = 60) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def http_bytes(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def upload_image(server: str, path: Path) -> str:
    """上传到 ComfyUI 的 input 目录，返回 LoadImage 应该填的文件名。"""
    boundary = "----AI3D" + uuid.uuid4().hex
    filename = path.name
    data = path.read_bytes()
    body = b""
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n" + data + b"\r\n"
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'.encode()
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{server}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        info = json.loads(resp.read())
    sub = info.get("subfolder") or ""
    name = info.get("name") or filename
    return f"{sub}/{name}" if sub else name


# --------------------------------------------------------------------------- #
# 工作流操作
# --------------------------------------------------------------------------- #
def load_workflow(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        wf = json.load(f)
    # 兼容误存成 UI 格式的文件：UI 格式有 "nodes" 列表，API 格式是以数字 ID 为键的字典
    if "nodes" in wf and isinstance(wf["nodes"], list):
        sys.exit(f"[×] {path} 是 UI 格式，不是 API 格式。请导出 API 格式（Save (API)）。")
    return wf


def find_node(wf: dict, class_type: str) -> tuple[str, dict]:
    hits = [(nid, n) for nid, n in wf.items() if n.get("class_type") == class_type]
    if not hits:
        raise KeyError(f"工作流里找不到节点类型 {class_type}")
    return hits[0]


def set_input(wf: dict, class_type: str, field: str, value) -> None:
    _, node = find_node(wf, class_type)
    node.setdefault("inputs", {})[field] = value


def get_models(wf: dict) -> dict:
    out = {}
    for class_type, field in (
        ("UNETLoader", "unet_name"),
        ("CLIPLoader", "clip_name"),
        ("VAELoader", "vae_name"),
        ("ImageOnlyCheckpointLoader", "ckpt_name"),
    ):
        for _, n in wf.items():
            if n.get("class_type") == class_type:
                if field in n.get("inputs", {}):
                    out[class_type] = n["inputs"][field]
    return out


# --------------------------------------------------------------------------- #
# 提交与轮询
# --------------------------------------------------------------------------- #
def comfy_version(server: str) -> str:
    try:
        stats = http_json(f"{server}/system_stats", timeout=10)
        return stats.get("system", {}).get("comfyui_version", "unknown")
    except Exception:
        return "unreachable"


def submit(server: str, wf: dict) -> str:
    payload = {"prompt": wf, "client_id": uuid.uuid4().hex}
    try:
        res = http_json(f"{server}/prompt", payload, timeout=60)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"提交被拒（HTTP {e.code}）：\n{detail}") from e
    if "prompt_id" not in res:
        raise RuntimeError(f"提交返回异常：{res}")
    if res.get("node_errors"):
        print("[!] 节点警告：", json.dumps(res["node_errors"], ensure_ascii=False)[:2000])
    return res["prompt_id"]


def wait_history(server: str, prompt_id: str, timeout: float) -> dict:
    t0 = time.time()
    last_msg = 0.0
    while time.time() - t0 < timeout:
        hist = http_json(f"{server}/history/{prompt_id}", timeout=30)
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                raise RuntimeError("ComfyUI 执行失败：\n" + json.dumps(msgs, ensure_ascii=False)[:4000])
            if status.get("completed") or entry.get("outputs"):
                return entry
        if time.time() - last_msg > 60:
            elapsed = int(time.time() - t0)
            print(f"    ...仍在跑（{elapsed}s）")
            last_msg = time.time()
        time.sleep(2)
    raise TimeoutError(f"{int(timeout)} 秒内没跑完，prompt_id={prompt_id}")


def free_models(server: str) -> None:
    try:
        http_json(f"{server}/free", {"unload_models": True, "free_memory": True}, timeout=30)
        print("[OK] 已请求 ComfyUI 卸载模型")
    except Exception as e:
        print(f"[!] /free 失败（不影响结果）：{e}")


def download_output(server: str, item: dict) -> bytes:
    q = urllib.parse.urlencode(
        {
            "filename": item.get("filename", ""),
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
    )
    return http_bytes(f"{server}/view?{q}", timeout=300)


def save_outputs(server: str, entry: dict, wf: dict, class_type: str, key: str,
                 outdir: Path, rename: str | None) -> list[Path]:
    node_id, _ = find_node(wf, class_type)
    outs = entry.get("outputs", {}).get(node_id, {})
    items = outs.get(key) or []
    saved = []
    for i, item in enumerate(items):
        data = download_output(server, item)
        if rename:
            name = rename if len(items) == 1 else f"{Path(rename).stem}_{i + 1:02d}{Path(rename).suffix}"
        else:
            name = item.get("filename") or f"output_{i:02d}.bin"
        dst = outdir / name
        dst.write_bytes(data)
        saved.append(dst)
        print(f"[OK] 保存 {dst}（{len(data) / 1e6:.2f} MB）")
    return saved


# --------------------------------------------------------------------------- #
# 各模式的工作流补丁
# --------------------------------------------------------------------------- #
def patch_common(wf: dict, args, mode: str) -> None:
    if args.seed is not None:
        set_input(wf, "KSampler", "seed", args.seed)
    if args.steps is not None:
        set_input(wf, "KSampler", "steps", args.steps)
    if args.cfg is not None:
        set_input(wf, "KSampler", "cfg", args.cfg)
    if mode == "t2i" and args.batch:
        # 只有 t2i 有空 latent；edit/hy3d 的 batch 必须为 1
        set_input(wf, "EmptyLatentImage", "batch_size", args.batch)
    for override in args.set or []:
        try:
            target, value = override.split("=", 1)
            class_type, field = target.split(".", 1)
        except ValueError:
            sys.exit(f"[×] --set 格式应为 节点类型.字段=值，收到：{override}")
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
        set_input(wf, class_type, field, value)


def build_job(mode: str, args, server: str) -> tuple[dict, dict]:
    wf_path = Path(args.workflow) if args.workflow else DEFAULT_API / f"{args.workflow_name}.json"
    wf = load_workflow(wf_path)
    meta = {"workflow": str(wf_path)}

    if mode in ("t2i", "edit"):
        set_input(wf, "TextEncodeQwenImage21", "prompt", args.prompt)
        if args.negative is not None:
            set_input(wf, "TextEncodeQwenImage21", "negative_prompt", args.negative)
        if args.resolution:
            set_input(wf, "TextEncodeQwenImage21", "resolution", args.resolution)
        if mode == "t2i" and (args.width or args.height):
            set_input(wf, "EmptyLatentImage", "width", args.width or 1024)
            set_input(wf, "EmptyLatentImage", "height", args.height or 1024)
        if mode == "edit":
            img = Path(os.path.expanduser(args.image)).resolve()
            if not img.is_file():
                sys.exit(f"[×] 找不到输入图：{img}")
            remote = upload_image(server, img)
            set_input(wf, "LoadImage", "image", remote)
            print(f"[OK] 已上传输入图 → {remote}")
            meta["input_image"] = str(img)
            meta["input_image_sha256"] = sha256(img)
    elif mode == "hy3d":
        img = Path(os.path.expanduser(args.image)).resolve()
        if not img.is_file():
            sys.exit(f"[×] 找不到输入图：{img}")
        remote = upload_image(server, img)
        set_input(wf, "LoadImage", "image", remote)
        print(f"[OK] 已上传输入图 → {remote}")
        meta["input_image"] = str(img)
        meta["input_image_sha256"] = sha256(img)
        if args.threshold is not None:
            set_input(wf, "VoxelToMesh", "threshold", args.threshold)
        if args.octree is not None:
            set_input(wf, "VAEDecodeHunyuan3D", "octree_resolution", args.octree)

    patch_common(wf, args, mode)
    return wf, meta


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def run_once(mode: str, args, server: str) -> list[Path]:
    wf, meta = build_job(mode, args, server)
    if args.dry_run:
        print(json.dumps(wf, ensure_ascii=False, indent=2))
        sys.exit(0)
    if args.dump_workflow:
        dump = Path(os.path.expanduser(args.dump_workflow))
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] 已写出本次实际工作流 {dump}")

    t0 = time.time()
    prompt_id = submit(server, wf)
    print(f"[OK] 已提交 prompt_id={prompt_id}")
    entry = wait_history(server, prompt_id, args.timeout)
    elapsed = time.time() - t0

    outdir = Path(os.path.expanduser(args.outdir)).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    if mode in ("t2i", "edit"):
        saved = save_outputs(server, entry, wf, "SaveImage", "images", outdir, args.name)
    else:
        saved = save_outputs(server, entry, wf, "SaveGLB", "3d", outdir, args.name)
        if not saved:
            raise RuntimeError("SaveGLB 没有返回任何文件，检查工作流是否保存到 output/AI3D/")
        for p in saved:
            if p.suffix.lower() == ".glb" and p.stat().st_size < 200_000:
                print(f"[!] 警告：{p.name} 只有 {p.stat().st_size / 1024:.0f} KB，可能有破面或空网格")

    if not saved:
        raise RuntimeError("任务完成但没有输出文件，检查工作流的输出节点是否连好")

    # 记录真正生效的采样参数（没在命令行覆盖时，用工作流里的值，而不是 None）
    ks = find_node(wf, "KSampler")[1].get("inputs", {})
    manifest = {
        "mode": mode,
        "prompt": args.prompt,
        "negative": args.negative,
        "seed": args.seed,
        "batch": getattr(args, "batch", 1),
        "steps": args.steps if args.steps is not None else ks.get("steps"),
        "cfg": args.cfg if args.cfg is not None else ks.get("cfg"),
        "sampler": ks.get("sampler_name"),
        "scheduler": ks.get("scheduler"),
        "models": get_models(wf),
        "comfyui_version": comfy_version(server),
        "prompt_id": prompt_id,
        "started_at": args._started_at,
        "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 1),
        "server": server,
        "outputs": [
            {"file": str(p), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in saved
        ],
        **meta,
    }
    manifest_path = outdir / f"run_{mode}_{now_stamp()}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 记录 {manifest_path}（耗时 {elapsed:.0f}s）")
    return saved


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    global SERVER
    parser = argparse.ArgumentParser(description="AI3D ComfyUI 命令行跑图工具")
    parser.add_argument("mode", choices=["t2i", "edit", "hy3d"])
    parser.add_argument("--server", default=SERVER_DEFAULT)
    parser.add_argument("--workflow", help="API 工作流 JSON 路径（优先于 --workflow-name）")
    parser.add_argument("--workflow-name", choices=["qwen_t2i", "qwen_edit", "hy3d"])
    parser.add_argument("--prompt")
    parser.add_argument("--default-prompt", action="store_true", help="保留工作流里的 prompt 不覆盖")
    parser.add_argument("--negative", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--cfg", type=float, default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--resolution", type=int, default=None, help="Qwen 参考图短边，默认 1024")
    parser.add_argument("--image", help="edit/hy3d 的输入图")
    parser.add_argument("--threshold", type=float, default=None, help="Hunyuan VoxelToMesh 阈值")
    parser.add_argument("--octree", type=int, default=None, help="Hunyuan 八叉树分辨率")
    parser.add_argument("--outdir", default="~/ai3d/renders")
    parser.add_argument("--name", help="输出文件重命名（单个输出时）")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--set", action="append", help="临时改节点字段，如 KSampler.cfg=1.0")
    parser.add_argument("--dry-run", action="store_true", help="只打印最终工作流，不提交")
    parser.add_argument("--dump-workflow", help="把实际提交的工作流另存一份")
    parser.add_argument("--no-free", action="store_true", help="结束时不卸载模型")
    args = parser.parse_args()

    if not args.workflow and not args.workflow_name:
        args.workflow_name = {"t2i": "qwen_t2i", "edit": "qwen_edit", "hy3d": "hy3d"}[args.mode]
    if not args.default_prompt and not args.prompt and args.mode != "hy3d":
        sys.exit("[×] 需要 --prompt（或 --default-prompt 用工作流自带的）")
    if args.mode in ("edit", "hy3d") and not args.image:
        sys.exit(f"[×] {args.mode} 需要 --image")
    if args.seed is None:
        args.seed = random.randint(0, 2**31 - 1)
        print(f"[i] 未指定 seed，本次随机用 {args.seed}（已写进 run.json）")

    SERVER = args.server.rstrip("/")
    args._started_at = dt.datetime.now().isoformat(timespec="seconds")

    ver = comfy_version(SERVER)
    if ver == "unreachable":
        sys.exit(f"[×] 连不上 ComfyUI：{SERVER}，先确认服务已启动（ss -ltn | grep 8188）")
    print(f"[i] ComfyUI {ver} @ {SERVER}")

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            run_once(args.mode, args, SERVER)
            break
        except Exception as e:
            print(f"[!] 第 {attempt}/{attempts} 次失败：{e}")
            if attempt == attempts:
                if not args.no_free:
                    free_models(SERVER)
                sys.exit(1)
            time.sleep(5)

    if not args.no_free:
        free_models(SERVER)


if __name__ == "__main__":
    main()
