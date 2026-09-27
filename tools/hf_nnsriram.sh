#!/usr/bin/env bash
# ===========================================================================
# `physics-video-lab/physics-video-assets` returns 404 and the org does not exist.
# But searching surfaced `nnsriram97/phyco_kubric` and `nnsriram97/phyco` --
# nnsriram97 is the author of the REFERENCE pipeline (github.com/nnsriram97/phyco-sim)
# named in the original brief, so their Hub repos are the strongest candidate.
#
# Output goes to a FILE because piping non-ASCII README text back through the
# ssh_ctl transport raises UnicodeEncodeError on the local side.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOK=$(cat "$HOME/.cache/huggingface/token" 2>/dev/null | tr -d '\r\n')
H=(-H "Authorization: Bearer $TOK")
OUT="$WS/tmp/hf_nnsriram.txt"
: > "$OUT"

{
echo "=== datasets + models by nnsriram97 ==="
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/datasets?author=nnsriram97&limit=100" 2>/dev/null \
  | tr ',' '\n' | grep -oE '"id":"[^"]*"'
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/models?author=nnsriram97&limit=100" 2>/dev/null \
  | tr ',' '\n' | grep -oE '"id":"[^"]*"'

echo
echo "=== tree: nnsriram97/phyco_kubric ==="
curl -sS -m 40 "${H[@]}" \
  "https://huggingface.co/api/datasets/nnsriram97/phyco_kubric/tree/main" 2>&1 | head -c 3000

echo
echo "=== README: nnsriram97/phyco_kubric ==="
curl -sS -m 40 "${H[@]}" \
  "https://huggingface.co/datasets/nnsriram97/phyco_kubric/raw/main/README.md" 2>&1 | head -100

echo
echo "=== README: nnsriram97/phyco (model) ==="
curl -sS -m 40 "${H[@]}" "https://huggingface.co/nnsriram97/phyco/raw/main/README.md" 2>&1 | head -60
} >> "$OUT" 2>&1

# ASCII-safe summary for the console
echo "=== ASCII summary ==="
grep -aE '"id"|error|404|=== ' "$OUT" | head -30 | sed 's/^/  /'
echo "  full text saved to $OUT ($(wc -c < "$OUT") bytes)"
