#!/usr/bin/env bash
# Get the tail of our working config so the new ones mirror it exactly.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== free_fall_gso.yaml (complete) ==="
cat -n "$REPO/configs/scenarios/free_fall_gso.yaml" | sed 's/^/  /'
