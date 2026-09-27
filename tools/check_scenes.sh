#!/usr/bin/env bash
# Which ReplicaCAD layouts exist, and which have been exported as environments?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
R="$WS/models/backgrounds/replicad"

echo "=== available scene layouts ==="
ls -1 "$R/configs/scenes" 2>/dev/null | sed 's/^/  /'

echo
echo "=== available stages ==="
ls -1 "$R/stages" 2>/dev/null | sed 's/^/  /'

echo
echo "=== available lighting configs ==="
ls -1 "$R/configs/lighting" 2>/dev/null | sed 's/^/  /'

echo
echo "=== which replicad environments are registered in the pipeline? ==="
grep -rn 'replicad\|Stage_v3\|frl_apartment' "$REPO/configs/assets.yaml" 2>/dev/null | sed 's/^/  /'
grep -rn 'replicad\|Stage_v3' "$REPO/configs/maps.yaml" 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=== our exported scene.blend files anywhere? ==="
find "$WS" -name 'scene.blend' -not -path '*/tmp/*' 2>/dev/null | sed "s|$WS/|  |"
