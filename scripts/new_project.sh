#!/bin/bash
# 建一个新项目目录，并复制一份提示词模板。
# 用法：~/ai3d/scripts/new_project.sh helmet01
set -euo pipefail

PROJECT="${1:-}"
if [ -z "$PROJECT" ]; then
  echo "用法：$0 <项目名>，例如 $0 helmet01" >&2
  exit 1
fi

ROOT="$HOME/ai3d"
DIR="$ROOT/projects/$PROJECT"
mkdir -p "$DIR/refs" "$DIR/textures"
mkdir -p "$ROOT/prompts"

PROMPT="$ROOT/prompts/${PROJECT}_concept.txt"
if [ ! -f "$PROMPT" ]; then
  if [ -f "$ROOT/prompts/_template_concept.txt" ]; then
    sed "s/<SUBJECT>/$PROJECT/g" "$ROOT/prompts/_template_concept.txt" > "$PROMPT"
  else
    printf 'A single %s, three-quarter view, plain white background, full object in frame, hard-surface design sheet, no text.\n' "$PROJECT" > "$PROMPT"
  fi
  echo "[OK] 新建提示词 $PROMPT"
fi

cat > "$DIR/project.json" <<EOF
{
  "project": "$PROJECT",
  "created": "$(date +%Y-%m-%d)",
  "subject": "$PROJECT",
  "pipeline": "Qwen-Image 2.1 UC -> Hunyuan3D 2.1 -> Blender 4.2 -> 4K still",
  "license_note": "Qwen UC is Qwen Research License (non-commercial). Hunyuan3D 2.1 has MAU/regional limits."
}
EOF

echo "[OK] 项目目录 $DIR"
echo "下一步："
echo "  1) 编辑 $PROMPT"
echo "  2) 跑概念图："
echo "     python3 ~/ai3d/scripts/comfy_run.py t2i --prompt \"\$(cat $PROMPT)\" --seed 42 --batch 4 --outdir $DIR/refs"
echo "  3) 选一张图后跑 3D（先复制成 hy_input.png）："
echo "     python3 ~/ai3d/scripts/comfy_run.py hy3d --image $DIR/refs/hy_input.png --outdir $DIR --name model.glb"
