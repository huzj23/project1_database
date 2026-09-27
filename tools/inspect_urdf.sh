#!/usr/bin/env bash
# Our GSO object.urdf fails to load in PyBullet ("failed to parse link").
# Inspect the URDF and the collision dir layout to find why.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
A="$REPO/assets/objects/gso_sootheze_cold_therapy_elephant"

echo "=== asset dir ==="
find "$A" -type f | sed "s#$A/#  #"

echo
echo "=== collision/model.urdf ==="
cat "$A/collision/model.urdf" | sed 's/^/  /'

echo
echo "=== source object.urdf (original GSO) ==="
cat "$WS/models/gso/Sootheze_Cold_Therapy_Elephant/object.urdf" | sed 's/^/  /'

echo
echo "=== compare: mentor's food_apple urdf (known working) ==="
cat "$REPO/assets/objects/food_apple/collision/model.urdf" | sed 's/^/  /'
