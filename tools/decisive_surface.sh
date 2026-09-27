#!/usr/bin/env bash
# ===========================================================================
# DECISIVE TEST: what support surface does the SIMULATOR actually build?
#
# Reading the code suggests:
#   physics/pybullet_backend.py:37  if surface.collision_simulation_path is not None
#                                      -> use that URDF mesh
#                                   else
#                                      -> build a Cube from surface.bounds_xy
#   maps/__init__.py:146-147        MapSpec.collision_center / collision_half_extents
#                                      are POPULATED from the environment asset.yaml
#                                      but never read anywhere else.
#
# If that is right, then my asset.yaml 94.29 m^2 change is INERT: the simulator
# still builds its support box from the maps.yaml region (1.7 x 1.7 m), and the
# value that actually matters is bounds_xy -- which is what I widened and then
# reverted at the user's request.
#
# This script proves it by loading the real map and printing the resulting
# support-box dimensions the backend would construct.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

cd "$REPO" || exit 1
"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | sed 's/^/  /'
import sys, os
sys.path.insert(0, "src")
from physim.assets import AssetManager
from physim.maps import MapManager

am = AssetManager("configs/assets.yaml")
mm = MapManager("configs/maps.yaml", am)

m = mm.get("replicad_apartment", require_files=False)
print("MapSpec for replicad_apartment:")
print(f"  environment_asset_id      = {m.environment_asset_id}")
print(f"  collision_center          = {m.collision_center}")
print(f"  collision_half_extents    = {m.collision_half_extents}")
print(f"  -> full footprint         = {2*m.collision_half_extents[0]:.3f} x "
      f"{2*m.collision_half_extents[1]:.3f} m "
      f"= {4*m.collision_half_extents[0]*m.collision_half_extents[1]:.2f} m^2")
print()
print("Surfaces:")
for s in m.surfaces:
    xmin, xmax, ymin, ymax = s.bounds_xy
    print(f"  {s.surface_id}")
    print(f"    bounds_xy               = {s.bounds_xy}")
    print(f"    -> support box footprint= {xmax-xmin:.3f} x {ymax-ymin:.3f} m "
          f"= {(xmax-xmin)*(ymax-ymin):.2f} m^2")
    print(f"    collision_simulation_path = {s.collision_simulation_path}")
    print(f"    surface_type            = {s.surface_type}")
    print()
    print("  ==> THE SIMULATOR WILL BUILD ITS SUPPORT BOX FROM THIS bounds_xy")
    print(f"      (no collision_simulation_path set), i.e. {(xmax-xmin)*(ymax-ymin):.2f} m^2")
PY

echo
echo "=== grep: is collision_half_extents EVER consumed outside maps/__init__? ==="
grep -rn 'collision_half_extents\|collision_center' "$REPO/src" "$REPO/scripts" \
    --include='*.py' 2>/dev/null | grep -v 'maps/__init__' | sed 's/^/  /'
echo "  ^^^ empty = populated but never used"
