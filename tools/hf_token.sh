#!/usr/bin/env bash
# ===========================================================================
# The dataset repo returns 401 Unauthorized (private or gated), and a token exists
# at ~/.cache/huggingface/token.  Test whether that token grants access, and if so
# read the repo's README (which the user says documents upload/download).
#
# NEVER print the token itself -- only its length and a masked prefix.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOK_FILE="$HOME/.cache/huggingface/token"
TOK=$(cat "$TOK_FILE" 2>/dev/null | tr -d '\r\n')
echo "=== token file ==="
stat -c '  mtime %y  size %s bytes' "$TOK_FILE"
echo "  length=${#TOK}  prefix=${TOK:0:3}****"

echo
echo "=== whoami with the token ==="
curl -sS -m 30 -H "Authorization: Bearer $TOK" https://huggingface.co/api/whoami-v2 2>&1 | head -c 600 | sed 's/^/  /'
echo

echo
echo "=== dataset API WITH token ==="
curl -sS -m 40 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets" 2>&1 \
  | head -c 1800 | sed 's/^/  /'
echo

echo
echo "=== repo tree WITH token ==="
curl -sS -m 40 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets/tree/main" 2>&1 \
  | head -c 3000 | sed 's/^/  /'
echo

echo
echo "=== README WITH token ==="
curl -sS -m 40 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/raw/main/README.md" 2>&1 \
  | head -120 | sed 's/^/  /'
