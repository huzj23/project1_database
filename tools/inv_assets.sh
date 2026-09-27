#!/usr/bin/env bash
# Inventory the assets that actually exist on the SERVER (where the pipeline runs).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== environments ==="
ls -1 "$REPO/assets/environments" 2>/dev/null | sed 's/^/  /'

echo
echo "=== objects ==="
ls -1 "$REPO/assets/objects" 2>/dev/null | sed 's/^/  /'

echo
echo "=== scenario configs ==="
ls -1 "$REPO/configs/scenarios" 2>/dev/null | sed 's/^/  /'

echo
echo "=== GSO objects we prepared ==="
ls -1 "$WS/models/gso" 2>/dev/null | sed 's/^/  /'

echo
echo "=== replicad scenes available ==="
ls -1 "$WS/models/backgrounds/replicad/configs/scenes" 2>/dev/null | sed 's/^/  /'

echo
echo "=== which environments are registered in configs/assets.yaml? ==="
sed -n '1,60p' "$REPO/configs/assets.yaml" 2>/dev/null | sed 's/^/  /'
