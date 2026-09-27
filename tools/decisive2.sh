#!/usr/bin/env bash
# Decisive test, correct signatures.  What support box does the simulator build?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | sed 's/^/  /'
import sys
sys.path.insert(0, "src")
from physim.assets import AssetManager
from physim.maps import MapManager

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
m = mm.get("replicad_apartment", require_files=False)

print("MapSpec.replicad_apartment")
print(f"  collision_center       = {m.collision_center}")
print(f"  collision_half_extents = {m.collision_half_extents}")
print(f"  -> asset.yaml footprint= {4*m.collision_half_extents[0]*m.collision_half_extents[1]:.2f} m^2")
print()
for s in m.surfaces:
    xmin, xmax, ymin, ymax = s.bounds_xy
    area = (xmax - xmin) * (ymax - ymin)
    print(f"  surface {s.surface_id}")
    print(f"    bounds_xy                = {s.bounds_xy}")
    print(f"    collision_simulation_path= {s.collision_simulation_path}")
    print(f"    -> support box = {(xmax-xmin):.3f} x {(ymax-ymin):.3f} m = {area:.2f} m^2")
    print(f"    ==> SIMULATOR USES THIS ({area:.2f} m^2), not the asset.yaml value")
PY
