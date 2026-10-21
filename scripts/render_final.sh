#!/bin/bash
# 最终渲染：命令行跑，不经过 MCP，避免超时。
# 用法：
#   ~/ai3d/scripts/render_final.sh helmet01            # 4K / 128 samples
#   ~/ai3d/scripts/render_final.sh helmet01 preview    # 1600×900 / 32 samples 小样
set -euo pipefail

PROJECT="${1:-helmet01}"
MODE="${2:-final}"
BLEND="$HOME/ai3d/blend/${PROJECT}.blend"
LOG_DIR="$HOME/ai3d/logs"
mkdir -p "$LOG_DIR" "$HOME/ai3d/renders"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/render_${PROJECT}_${MODE}_${STAMP}.log"

BLENDER="$(command -v blender || true)"
[ -z "$BLENDER" ] && BLENDER="$HOME/.local/bin/blender"
if [ ! -x "$BLENDER" ]; then
  echo "[×] 找不到 Blender，试过 PATH 和 ~/.local/bin/blender" >&2
  exit 1
fi
if [ ! -f "$BLEND" ]; then
  echo "[×] 找不到 $BLEND，先在 Blender 里跑完 studio + render 阶段" >&2
  exit 1
fi

if [ "$MODE" = "preview" ]; then
  OUT="$HOME/ai3d/renders/${PROJECT}_preview.png"
  EXPR="import bpy
s = bpy.context.scene
s.render.resolution_x = 1600
s.render.resolution_y = 900
s.render.resolution_percentage = 100
s.cycles.samples = 32
s.cycles.adaptive_threshold = 0.03
s.cycles.use_denoising = True
s.render.image_settings.file_format = 'PNG'
s.render.image_settings.color_mode = 'RGBA'
s.render.image_settings.color_depth = '16'
s.render.filepath = r'${OUT}'
bpy.ops.render.render(write_still=True)
print('[AI3D] preview written', s.render.filepath)"
else
  OUT="$HOME/ai3d/renders/${PROJECT}_4k.png"
  EXPR="import bpy
s = bpy.context.scene
s.render.resolution_x = 3840
s.render.resolution_y = 2160
s.render.resolution_percentage = 100
s.cycles.samples = 128
s.cycles.adaptive_threshold = 0.01
s.cycles.use_denoising = True
s.render.image_settings.file_format = 'PNG'
s.render.image_settings.color_mode = 'RGBA'
s.render.image_settings.color_depth = '16'
s.render.filepath = r'${OUT}'
bpy.ops.render.render(write_still=True)
print('[AI3D] final written', s.render.filepath)"
fi

echo "[i] Blender: $BLENDER"
echo "[i] 工程:   $BLEND"
echo "[i] 输出:   $OUT"
echo "[i] 日志:   $LOG"
echo "[i] 开始渲染（本机 4K 实测约 1 分钟，显存不足会明显变慢）"

START_TS=$(date +%s)
if ! "$BLENDER" -b "$BLEND" --python-expr "$EXPR" > "$LOG" 2>&1; then
  echo "[×] 渲染失败，最后 30 行日志：" >&2
  tail -30 "$LOG" >&2
  exit 1
fi
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

if [ ! -s "$OUT" ]; then
  echo "[×] 日志说完成了，但输出文件不存在或为空：$OUT" >&2
  tail -30 "$LOG" >&2
  exit 1
fi

SIZE=$(stat -c%s "$OUT")
echo "[OK] 写出 $OUT（$(echo "scale=1; $SIZE/1048576" | bc) MB）"
file "$OUT"
if grep -qiE 'CUDA error|out of memory|Error:' "$LOG"; then
  echo "[!] 日志里有错误关键词，虽然出图了，建议检查：$LOG"
fi
echo "[OK] 日志：$LOG"

# 把本次渲染写进 projects/<name>/run.json，保证成品可追溯
python3 - "$PROJECT" "$MODE" "$OUT" "$SIZE" "$DURATION" "$LOG" <<'PY'
import datetime
import json
import pathlib
import sys

proj, mode, out, size, dur, log = sys.argv[1:7]
meta = pathlib.Path.home() / "ai3d" / "projects" / proj / "run.json"
data = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {"project": proj}
stages = data.setdefault("stages", {})
key = "render_preview" if mode == "preview" else "render"
stages[key] = {
    "time": datetime.datetime.now().isoformat(timespec="seconds"),
    "mode": mode,
    "output": out,
    "bytes": int(size),
    "resolution": [1600, 900] if mode == "preview" else [3840, 2160],
    "samples": 32 if mode == "preview" else 128,
    "adaptive_threshold": 0.03 if mode == "preview" else 0.01,
    "color_depth": 16,
    "duration_sec": int(dur),
    "log": log,
}
meta.parent.mkdir(parents=True, exist_ok=True)
meta.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[OK] run.json 已记录 {key}，耗时 {dur}s：{meta}")
PY
