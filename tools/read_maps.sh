#!/usr/bin/env bash
# Read the full maps.yaml structure (earlier grep was truncated by head).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== all region_ids ==="
grep -n 'region_id' configs/maps.yaml | sed 's/^/  /'

echo
echo "=== the replicad_apartment map block ==="
awk '/^  replicad_apartment:/,/^  [a-z_]+:$/' configs/maps.yaml | head -60 | sed 's/^/  /'

echo
echo "=== T1 progress ==="
for c in "$REPO"/cache/*/seed-*/x1/images; do
  [ -d "$c" ] || continue
  echo "  $c: $(ls $c 2>/dev/null | wc -l) frames"
done
cat "$WS/tmp/t1_render_stdout.log" 2>/dev/null | tr -d '\r'
