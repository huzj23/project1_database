#!/usr/bin/env bash
# Print the replicad_apartment region block from the SERVER's maps.yaml
# (the local checkout is stale; all edits are applied server-side).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== total lines ==="
wc -l < "$REPO/configs/maps.yaml"
echo
echo "=== replicad_apartment block (from its map entry to EOF) ==="
awk '/^  replicad_apartment:/{f=1} f' "$REPO/configs/maps.yaml" | sed 's/^/  /'
