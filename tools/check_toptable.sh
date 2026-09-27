#!/usr/bin/env bash
# The turntable needs a `table_top` surface, but replicad_apartment only declares
# `floor`.  Look at the existing table_top template and the selection logic.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== existing table_top region (template, lines 38-56) ==="
sed -n '36,56p' "$REPO/configs/maps.yaml" | sed 's/^/  /'

echo
echo "=== select_surface: how are allowed_types enforced? ==="
grep -n 'def select_surface' -A40 "$REPO/src/physim/scenarios/common.py" | sed 's/^/  /'
