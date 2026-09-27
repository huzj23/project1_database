#!/usr/bin/env bash
# Trace: environment asset.yaml `collision` -> MapSpec.collision_center/half_extents
#        -> is it actually used by the physics backend?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== who READS collision_center / collision_half_extents? ==="
grep -rn 'collision_center\|collision_half_extents' "$REPO/src/physim/" "$REPO/scripts/" 2>/dev/null | sed 's/^/  /'

echo
echo "=== MapSpec definition ==="
sed -n '79,98p' "$REPO/src/physim/maps/__init__.py" | sed 's/^/  /'

echo
echo "=== the branch that builds the support body (lines 37-76) ==="
sed -n '36,40p' "$REPO/src/physim/physics/pybullet_backend.py" | sed 's/^/  /'
echo "  ..."
echo "  -> uses surface.collision_simulation_path if set, ELSE surface.bounds_xy"

echo
echo "=== so: for replicad_apartment, is collision_simulation_path set? ==="
grep -n 'collision:' -A4 "$REPO/configs/maps.yaml" | sed -n '1,20p' | sed 's/^/  /'
echo
echo "=== replicad region block again (no 'collision:' key = box path) ==="
sed -n '/replicad_apartment:/,/^  [a-z]/p' "$REPO/configs/maps.yaml" | sed 's/^/  /'
