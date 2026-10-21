#!/bin/bash
set -euo pipefail

BASE_QWEN="https://hf-mirror.com/abenzerps/Qwen-Image-2.1-Uncensored-Quantized/resolve/main"
BASE_HY="https://hf-mirror.com/Comfy-Org/hunyuan3D_2.1_repackaged/resolve/main"
DEST="$HOME/ai3d/downloads/qwen-uc"
HY_DEST="$HOME/ComfyUI/models/checkpoints"

mkdir -p "$DEST/text_encoders" "$DEST/vae" "$HY_DEST"

fetch() {
  local url="$1" out="$2" expected="${3:-}"
  if [ -n "$expected" ] && [ -f "$out" ] && [ "$(stat -c%s "$out")" = "$expected" ]; then
    echo "[skip] $out already complete"
    return 0
  fi
  echo "[get ] $out"
  if ! curl -L --fail --retry 8 --retry-delay 5 --connect-timeout 20 -C - -o "$out" "$url"; then
    echo "[warn] resume failed for $out, retrying from scratch"
    rm -f "$out"
    curl -L --fail --retry 8 --retry-delay 5 --connect-timeout 20 -o "$out" "$url"
  fi
}

fetch "$BASE_QWEN/SHA256SUMS" "$DEST/SHA256SUMS"
fetch "$BASE_QWEN/qwen-image-2.1-UC-int8_convrot.safetensors" \
  "$DEST/qwen-image-2.1-UC-int8_convrot.safetensors" 7256796840
fetch "$BASE_QWEN/text_encoders/qwen3vl_8b_int8_convrot.safetensors" \
  "$DEST/text_encoders/qwen3vl_8b_int8_convrot.safetensors" 9350798360
fetch "$BASE_QWEN/vae/qwen_image_2.1_vae_bf16.safetensors" \
  "$DEST/vae/qwen_image_2.1_vae_bf16.safetensors" 675509688

echo "[check] sizes"
stat -c '%s  %n' "$DEST/qwen-image-2.1-UC-int8_convrot.safetensors" \
  "$DEST/text_encoders/qwen3vl_8b_int8_convrot.safetensors" \
  "$DEST/vae/qwen_image_2.1_vae_bf16.safetensors"

echo "[get ] hunyuan_3d_v2.1.safetensors"
fetch "$BASE_HY/hunyuan_3d_v2.1.safetensors" "$HY_DEST/hunyuan_3d_v2.1.safetensors" 7365943290

echo "[done] all downloads finished"
