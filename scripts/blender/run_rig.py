#!/usr/bin/env python3
"""AI3D 绑定流水线一键入口。

一条命令按顺序做四步：
    1. 32_rig_parts.py   搭骨架 + 绑定 + 保存 .blend + 导出 GLB
    2. 35_verify_rig_glb.py  重新导入 GLB，机器验收变形
    3. 33_rig_pose.py    渲染休息/动作/头部预览
    4. 34_rig_sheet.py   拼验收板

最后写一份 <rig>/rig_report.json，记录每一步耗时、产物大小和验收结果。
换模型时只改 <project>/rig.json；脚本、命令都不用改。

用法：
    python3 scripts/blender/run_rig.py --project dragon01
    python3 scripts/blender/run_rig.py --project dragon01 --skip-pose
    python3 scripts/blender/run_rig.py --project dragon01 --build-only
    python3 scripts/blender/run_rig.py --project dragon01 --verify-only

常用环境变量：
    AI3D_BLENDER   Blender 可执行文件（默认 ~/.local/bin/blender）
    AI3D_PYTHON    带 Pillow 的 Python（默认自动找）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
PROJECTS_ROOT = HOME / "ai3d" / "projects"
SCRIPTS = Path(__file__).resolve().parent


def log(msg: str) -> None:
    print(f"[AI3D pipeline] {msg}", flush=True)


def die(msg: str) -> None:
    raise SystemExit(f"[×] {msg}")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} 不是合法 JSON：第 {e.lineno} 行 {e.msg}")


def resolve_project(value: str) -> Path:
    p = Path(value).expanduser()
    if p.is_dir():
        return p.resolve()
    if p.is_absolute():
        return p.resolve()
    return (PROJECTS_ROOT / p).resolve()


def find_blender(explicit: str | None) -> Path:
    cands = [
        explicit,
        os.environ.get("AI3D_BLENDER"),
        str(HOME / ".local/bin/blender"),
        shutil.which("blender"),
    ]
    for c in cands:
        if not c:
            continue
        p = Path(c).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
    die("找不到 Blender。请用 --blender 指定，或设置 AI3D_BLENDER")


def find_python(explicit: str | None) -> str:
    cands = [
        explicit,
        os.environ.get("AI3D_PYTHON"),
        sys.executable,
        shutil.which("python3"),
        str(HOME / "ComfyUI/venv/bin/python"),
    ]
    seen = set()
    for c in cands:
        if not c or c in seen:
            continue
        seen.add(c)
        p = Path(c).expanduser()
        if not p.is_file():
            continue
        try:
            r = subprocess.run([str(p), "-c", "import PIL"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=20)
        except Exception:
            continue
        if r.returncode == 0:
            return str(p)
    die("找不到带 Pillow 的 Python。请用 --python 指定，"
        "例如 ~/ComfyUI/venv/bin/python")


def size_of(path: Path) -> int | None:
    return path.stat().st_size if path.is_file() else None


def human_bytes(n: int | None) -> str:
    if n is None:
        return "?"
    if n < 1_000_000:
        return f"{n / 1e3:.1f} KB"
    return f"{n / 1e6:.1f} MB"


def artifact(path: Path, **extra) -> dict:
    data = {
        "path": str(path),
        "exists": path.is_file(),
        "bytes": size_of(path),
    }
    data.update(extra)
    return data


def source_blend(cfg: dict, project: Path) -> Path:
    raw = cfg.get("source_blend")
    if raw:
        p = Path(raw).expanduser()
        return (p if p.is_absolute() else project / p).resolve()
    for p in (project / "parts" / f"{project.name}_parts.blend",
              project / "parts" / "parts.blend"):
        if p.is_file():
            return p
    found = sorted((project / "parts").glob("*.blend"))
    return found[0] if found else project / "parts" / f"{project.name}_parts.blend"


# --------------------------------------------------------------------------- #
# 命令行
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="AI3D 绑定流水线：骨架 → 验收 → 预览 → 验收板")
    ap.add_argument("--project", default=os.environ.get("AI3D_PROJECT", "dragon01"),
                    help="项目名或项目目录，默认 dragon01")
    ap.add_argument("--config", default=None, help="默认 <project>/rig.json")
    ap.add_argument("--out", default=None, help="默认 <project>/rig")
    ap.add_argument("--blender", default=None)
    ap.add_argument("--python", default=None, help="带 Pillow 的 Python")
    ap.add_argument("--res", type=int, default=1400, help="预览单张边长")
    ap.add_argument("--report", default=None, help="默认 <out>/rig_report.json")
    ap.add_argument("--build-only", action="store_true", help="只搭骨架/导出")
    ap.add_argument("--verify-only", action="store_true", help="只做 GLB 验收")
    ap.add_argument("--skip-verify", action="store_true")
    ap.add_argument("--skip-pose", action="store_true")
    ap.add_argument("--skip-sheet", action="store_true")
    ap.add_argument("--no-export", action="store_true", help="不导出 GLB（会跳过验收）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令，不执行")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    started = time.time()
    project = resolve_project(args.project)
    if not project.is_dir():
        die(f"项目目录不存在：{project}")

    config = Path(args.config).expanduser().resolve() if args.config else project / "rig.json"
    if not config.is_file():
        die(f"找不到骨架配置：{config}\n格式参考 projects/dragon01/rig.json")
    cfg = read_json(config)
    stem = cfg.get("file_stem") or f"{project.name}_rig"
    out = Path(args.out).expanduser().resolve() if args.out else project / "rig"
    out.mkdir(parents=True, exist_ok=True)

    blend = out / f"{stem}.blend"
    manifest = out / "rig_manifest.json"
    glb = out / "glb" / f"{stem}.glb"
    preview = out / "preview"
    sheet = preview / f"{stem}_sheet.png"
    verify_report = out / "verify_report.json"
    report_path = Path(args.report).expanduser().resolve() if args.report else out / "rig_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    blender = find_blender(args.blender)
    py = find_python(args.python)
    source = source_blend(cfg, project)

    log(f"项目 {project.name}；配置 {config}")
    log(f"Blender {blender}")
    log(f"Python  {py}")

    steps: dict[str, dict] = {}
    artifacts: dict[str, dict] = {}
    current = {"name": None}

    def run_cmd(name: str, cmd: list[str], hint: str) -> None:
        log(f"—— {name} ——")
        log("$ " + shlex.join(cmd))
        current["name"] = name
        t0 = time.time()
        if args.dry_run:
            steps[name] = {"ok": None, "seconds": 0, "cmd": shlex.join(cmd),
                           "dry_run": True}
            return
        rc = subprocess.run(cmd).returncode
        seconds = round(time.time() - t0, 1)
        if rc != 0:
            steps[name] = {"ok": False, "seconds": seconds,
                           "cmd": shlex.join(cmd), "returncode": rc}
            write_report(report_path, project, config, out, steps, artifacts,
                         started, ok=False, failed_step=name, hint=hint)
            print(f"\n[×] 第「{name}」步失败（退出码 {rc}）。", flush=True)
            print(f"    先查：{hint}", flush=True)
            print(f"    机器报告：{report_path}", flush=True)
            raise SystemExit(rc or 1)
        steps[name] = {"ok": True, "seconds": seconds, "cmd": shlex.join(cmd)}
        log(f"{name} 完成，用时 {seconds:.1f} s")

    if not source.is_file() and not args.verify_only:
        die(f"找不到分件工程：{source}\n检查 rig.json 的 source_blend")

    if args.verify_only:
        if not glb.is_file():
            die(f"找不到 GLB：{glb}")
        run_cmd("GLB 验收", [
            str(blender), "-b", "--python", str(SCRIPTS / "35_verify_rig_glb.py"),
            "--", "--glb", str(glb), "--manifest", str(manifest),
            "--report", str(verify_report),
        ], "先跑 --build-only；确认 rig_manifest.json 和 GLB 是同一批产物")
    elif args.build_only:
        cmd = [
            str(blender), "-b", str(source),
            "--python", str(SCRIPTS / "32_rig_parts.py"),
            "--", "--config", str(config), "--out", str(out),
        ]
        if args.no_export:
            cmd.append("--no-export")
        run_cmd("搭骨架与绑定", cmd,
                "检查 rig.json 的件名是否和分件工程一致；"
                "可先打开 parts/dragon01_parts.blend 对照 Outliner")
    else:
        cmd = [
            str(blender), "-b", str(source),
            "--python", str(SCRIPTS / "32_rig_parts.py"),
            "--", "--config", str(config), "--out", str(out),
        ]
        if args.no_export:
            cmd.append("--no-export")
        run_cmd("搭骨架与绑定", cmd,
                "检查 rig.json 的件名/骨名；脚本会打印缺哪个件")

        if args.no_export:
            log("--no-export：跳过 GLB 验收")
        elif not args.skip_verify:
            run_cmd("GLB 验收", [
                str(blender), "-b", "--python", str(SCRIPTS / "35_verify_rig_glb.py"),
                "--", "--glb", str(glb), "--manifest", str(manifest),
                "--report", str(verify_report),
            ], "看 35 输出的第一条 [×]；常见是权重和≠1 或骨树和清单不一致")

        if not args.skip_pose:
            run_cmd("姿态预览", [
                str(blender), "-b", str(blend),
                "--python", str(SCRIPTS / "33_rig_pose.py"),
                "--", "--manifest", str(manifest), "--out", str(preview),
                "--res", str(args.res),
            ], "确认 .blend 已生成；姿势表里的骨名要在 rig.json preview.pose 里")
        else:
            log("--skip-pose：跳过姿态预览")

        if not args.skip_sheet:
            if not preview.is_dir() or not any(preview.glob("rig_*.png")):
                log("⚠ 没有预览图，跳过验收板")
            else:
                run_cmd("拼验收板", [
                    py, str(SCRIPTS / "34_rig_sheet.py"),
                    "--config", str(config), "--manifest", str(manifest),
                    "--preview", str(preview), "--out", str(sheet),
                ], "确认 Python 带 Pillow；先跑姿态预览")
        else:
            log("--skip-sheet：跳过验收板")

    if args.dry_run:
        print("\n[OK] 演练完成：上面的命令没有执行，也没有写报告。", flush=True)
        return

    artifacts = {
        "rig_blend": artifact(blend),
        "manifest": artifact(manifest),
        "glb": artifact(glb),
        "sheet": artifact(sheet),
        "verify_report": artifact(verify_report),
        "preview_images": [
            artifact(p) for p in sorted(preview.glob("rig_*.png"))
        ] if preview.is_dir() else [],
    }
    write_report(report_path, project, config, out, steps, artifacts,
                 started, ok=True)

    elapsed = time.time() - started
    print("\n" + "=" * 68, flush=True)
    print(f"[OK] 绑定流水线完成：{sum(1 for s in steps.values() if s.get('ok'))} 步 / "
          f"{elapsed:.1f} s", flush=True)
    for label, key in (("主工程", "rig_blend"), ("GLB", "glb"),
                       ("清单", "manifest"), ("验收板", "sheet"),
                       ("机器报告", "verify_report")):
        a = artifacts[key]
        if a["exists"]:
            print(f"  {label:6s} {a['path']}  ({human_bytes(a['bytes'])})", flush=True)
        else:
            print(f"  {label:6s} （未生成）", flush=True)
    print(f"  汇总     {report_path}", flush=True)
    print("=" * 68, flush=True)


def write_report(path: Path, project: Path, config: Path, out: Path,
                 steps: dict, artifacts: dict, started: float,
                 ok: bool, failed_step: str | None = None,
                 hint: str | None = None) -> None:
    report = {
        "version": 1,
        "project": project.name,
        "config": str(config),
        "out": str(out),
        "started": dt.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "finished": dt.datetime.now().isoformat(timespec="seconds"),
        "duration_s": round(time.time() - started, 1),
        "ok": ok,
        "failed_step": failed_step,
        "hint": hint,
        "steps": steps,
        "artifacts": artifacts,
    }
    verify_path = Path(artifacts.get("verify_report", {}).get("path", ""))
    if verify_path.is_file():
        try:
            report["verify"] = json.loads(verify_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
