#!/usr/bin/env bash
# CRITICAL CHECK: the physics backend builds its support surface from
# `surface.bounds_xy` (a maps.yaml region), NOT from asset.yaml `collision`.
# If so, my 94.29 m^2 asset.yaml change is NOT what the simulator uses, and the
# real support patch is still the 1.7 x 1.7 m pinned region.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== is asset.collision referenced anywhere in the physics path? ==="
grep -rn 'asset.collision\|collision_type\|half_extents' \
    "$REPO/src/physim/physics/pybullet_backend.py" | sed 's/^/  /'

echo
echo "=== where does surface.bounds_xy come from? ==="
grep -rn 'bounds_xy\|collision_simulation_path\|surface_type\|regions' \
    "$REPO/src/physim/maps/__init__.py" 2>/dev/null | head -25 | sed 's/^/  /'

echo
echo "=== does anything read the ENVIRONMENT asset.yaml collision? ==="
grep -rn 'environment_asset_id\|collision' "$REPO/src/physim/maps/__init__.py" 2>/dev/null | head -25 | sed 's/^/  /'

echo
echo "=== the maps loader: how regions become surfaces ==="
grep -n 'class \|def ' "$REPO/src/physim/maps/__init__.py" 2>/dev/null | sed 's/^/  /'
