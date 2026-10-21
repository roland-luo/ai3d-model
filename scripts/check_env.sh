#!/bin/bash
# 环境自检：版本、端口、权重、GPU、显存、磁盘。
set -uo pipefail

ROOT="$HOME/ai3d"
fail=0
ok()   { echo "[OK]   $*"; }
warn() { echo "[!]    $*"; }
bad()  { echo "[×]    $*"; fail=1; }

echo "== ComfyUI =="
STATS=$(curl -s --max-time 5 http://127.0.0.1:8188/system_stats || true)
if [ -z "$STATS" ]; then
  bad "8188 没响应，ComfyUI 没开？"
else
  VER=$(echo "$STATS" | python3 -c 'import json,sys; print(json.load(sys.stdin)["system"]["comfyui_version"])' 2>/dev/null || echo "?")
  ok "ComfyUI $VER @ 8188"
fi

echo "== 权重 =="
check_file() {
  local f="$1" expect="$2" label="$3"
  if [ ! -f "$f" ]; then bad "$label 缺失：$f"; return; fi
  local size; size=$(stat -c%s "$f")
  if [ -n "$expect" ] && [ "$size" != "$expect" ]; then
    bad "$label 大小不对：$size（应为 $expect）"
  else
    ok "$label $(echo "scale=2; $size/1073741824" | bc) GB"
  fi
}
check_file "$HOME/ComfyUI/models/diffusion_models/qwen-image-2.1-UC-int8_convrot.safetensors" 7256796840 "Qwen DiT"
check_file "$HOME/ComfyUI/models/text_encoders/qwen3vl_8b_int8_convrot.safetensors" 9350798360 "Qwen 文本编码器"
check_file "$HOME/ComfyUI/models/vae/qwen_image_2.1_vae_bf16.safetensors" 675509688 "Qwen VAE"
check_file "$HOME/ComfyUI/models/checkpoints/hunyuan_3d_v2.1.safetensors" 7365943290 "Hunyuan3D 2.1"

echo "== Blender =="
BL=$(command -v blender || true); [ -z "$BL" ] && BL="$HOME/.local/bin/blender"
if [ -x "$BL" ]; then ok "Blender $("$BL" --version 2>/dev/null | head -1)"; else bad "Blender 不在 PATH"; fi
if ss -ltn 2>/dev/null | grep -q ':9876 '; then
  ok "Blender MCP 9876 在听"
else
  warn "9876 没在听：先在 Blender 里打开 MCP 插件 / Start server"
fi

echo "== GPU =="
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,memory.used,temperature.gpu --format=csv,noheader | sed 's/^/       /'
  if nvidia-smi | grep -qi 'xid'; then warn "nvidia-smi 输出里出现 Xid，注意掉卡史"; fi
else
  bad "没有 nvidia-smi"
fi

echo "== 磁盘 =="
df -h "$HOME" | tail -1

echo "== 最近一次渲染 =="
ls -lt "$ROOT/renders" 2>/dev/null | head -4

if [ "$fail" -eq 1 ]; then
  echo; echo "有硬性检查没通过，按上面 [×] 处理。"
  exit 1
fi
echo; echo "环境自检通过。"
