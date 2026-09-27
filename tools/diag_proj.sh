#!/usr/bin/env bash
# Why does free_fall placement fail with edge_margin 1.20?
# Check what travel_distance free_fall passes to sample_position.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== free_fall.py sample_position call + surrounding logic ==="
grep -n 'sample_position' -B22 -A12 src/physim/scenarios/free_fall.py | sed 's/^/  /'

echo
echo "=== the actual bounds and margin math ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys; sys.path.insert(0,"src")
from physim.assets import AssetManager
from physim.maps import MapManager
am=AssetManager("configs/assets.yaml","assets"); mm=MapManager("configs/maps.yaml",am)
ms=mm.get("replicad_apartment", require_files=True)
s=ms.surfaces[0]
x0,x1,y0,y1=s.bounds_xy
print(f"  bounds_xy = {s.bounds_xy}  -> {x1-x0:.2f} x {y1-y0:.2f} m")
for aid in ("gso_mad_gab_refresh_card_game","gso_ecoforms_plant_container_gp16a_coral"):
    a=am.get(aid)
    print(f"  {aid}: radius={a.radius:.4f} support_h={a.support_height:.4f}")
PY
