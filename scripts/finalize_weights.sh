#!/bin/bash
# 下载完成后：校验 → 结构检查 → 移到 ComfyUI 模型目录。
# 这个仓库的 SHA256SUMS 里没有 INT8 DiT，所以 DiT 的 sha256 取自 Hugging Face 的 LFS 元数据。
set -euo pipefail

Q="$HOME/ai3d/downloads/qwen-uc"
HY="$HOME/ComfyUI/models/checkpoints/hunyuan_3d_v2.1.safetensors"
DIT="$Q/qwen-image-2.1-UC-int8_convrot.safetensors"
TE="$Q/text_encoders/qwen3vl_8b_int8_convrot.safetensors"
VAE="$Q/vae/qwen_image_2.1_vae_bf16.safetensors"

echo "== 1. 大小 =="
check_size() {
  local f="$1" want="$2" name="$3"
  [ -f "$f" ] || { echo "[×] 缺文件 $f"; exit 1; }
  local got; got=$(stat -c%s "$f")
  if [ "$got" != "$want" ]; then
    echo "[×] $name 大小 $got，应为 $want"; exit 1
  fi
  echo "[OK] $name $got 字节"
}
check_size "$DIT" 7256796840 "Qwen DiT INT8"
check_size "$TE"  9350798360 "Qwen 文本编码器 INT8"
check_size "$VAE" 675509688  "Qwen VAE BF16"
check_size "$HY"  7365943290 "Hunyuan3D 2.1"

echo "== 2. SHA256 =="
EXPECTED="$Q/expected.sha256"
cat > "$EXPECTED" <<'EOF'
5bc5a6c007eff1e0d4004344a24c4af966b9d2c83d142e613b0d456ccceb19ae  qwen-image-2.1-UC-int8_convrot.safetensors
8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f  text_encoders/qwen3vl_8b_int8_convrot.safetensors
bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9  vae/qwen_image_2.1_vae_bf16.safetensors
EOF
( cd "$Q" && sha256sum -c expected.sha256 )

echo "== 3. Hunyuan SHA256（单独算，约 7.4GB）=="
echo "5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72  $HY" | sha256sum -c -

echo "== 4. safetensors 结构 =="
"$HOME/ComfyUI/venv/bin/python" - "$DIT" "$TE" "$VAE" "$HY" <<'PY'
import json, os, struct, sys
for path in sys.argv[1:]:
    total = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(8)
    n = struct.unpack("<Q", head)[0]
    with open(path, "rb") as f:
        f.read(8)
        meta = json.loads(f.read(n))
    end = max(v["data_offsets"][1] for k, v in meta.items() if k != "__metadata__")
    assert 8 + n + end <= total, f"{path} 数据越界"
    print(f"[OK] {os.path.basename(path)} 张量 {len(meta)-1} 个，头部 {n} 字节")
PY

echo "== 5. 移入 ComfyUI =="
mkdir -p "$HOME/ComfyUI/models/diffusion_models" "$HOME/ComfyUI/models/text_encoders" \
         "$HOME/ComfyUI/models/vae" "$HOME/ComfyUI/models/checkpoints"
mv -f "$DIT" "$HOME/ComfyUI/models/diffusion_models/"
mv -f "$TE"  "$HOME/ComfyUI/models/text_encoders/"
mv -f "$VAE" "$HOME/ComfyUI/models/vae/"
# Hunyuan 已在 checkpoints（下载脚本直接写那里）

find "$Q" "$HOME/ComfyUI/models" -name '*.incomplete' -print -delete || true
{
  echo "verified $(date -Is)"
  sha256sum "$HOME/ComfyUI/models/diffusion_models/qwen-image-2.1-UC-int8_convrot.safetensors"
  sha256sum "$HOME/ComfyUI/models/text_encoders/qwen3vl_8b_int8_convrot.safetensors"
  sha256sum "$HOME/ComfyUI/models/vae/qwen_image_2.1_vae_bf16.safetensors"
  sha256sum "$HY"
} > "$HOME/ai3d/logs/weights_verified.txt"

echo "[OK] 全部校验通过，权重就位。记录：$HOME/ai3d/logs/weights_verified.txt"
