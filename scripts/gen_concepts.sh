#!/bin/bash
# 一次生成 4 张概念图（batch 1，逐张跑，避免显存峰值）。
# 用法：~/ai3d/scripts/gen_concepts.sh helmet01 [起始种子]
set -euo pipefail

PROJECT="${1:-helmet01}"
SEED_BASE="${2:-101}"
PROMPT_FILE="$HOME/ai3d/prompts/${PROJECT}_concept.txt"
OUT="$HOME/ai3d/projects/$PROJECT/refs"

if [ ! -f "$PROMPT_FILE" ]; then
  echo "[×] 没有提示词文件 $PROMPT_FILE，先跑 new_project.sh $PROJECT" >&2
  exit 1
fi
mkdir -p "$OUT"

for i in 1 2 3 4; do
  SEED=$((SEED_BASE + i * 101))
  EXTRA="--no-free"
  [ "$i" -eq 4 ] && EXTRA=""
  echo
  echo "===== 第 $i/4 张，seed=$SEED ====="
  python3 "$HOME/ai3d/scripts/comfy_run.py" t2i \
    --prompt "$(cat "$PROMPT_FILE")" \
    --seed "$SEED" --batch 1 --outdir "$OUT" $EXTRA
done

echo
echo "[OK] 4 张概念图在 $OUT"
ls -lt "$OUT" | head -8
