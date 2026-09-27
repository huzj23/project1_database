#!/usr/bin/env bash
# ===========================================================================
# Fix free_fall outside_surface_bounds.
#
# MEASURED: with drop 1.6-2.4 m the actor travelled 1.632 m (drop_distance
# 1.583 m) and drifted ~0.40 m horizontally after the bounce, leaving the
# placement rectangle.  free_fall reserves travel_distance = 0 when sampling
# (the motion is vertical), so the actor may start near the edge and the
# post-bounce drift then carries it out.
#
# The mentor's own free_fall.yaml is the proven scale:
#     drop_height_absolute_range: [0.45, 1.20]
#     horizontal_speed_range:     [0.03, 0.12]
#     edge_margin:                0.15
# A 2.4 m drop is 2x his maximum and is what broke the bound.
#
# Fix: adopt his proven scale (a visible drop, still larger than his mean), give
# the actor a real but small horizontal velocity as he does, and increase the
# placement margin so post-bounce drift stays inside.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY'
p = "configs/scenarios/free_fall_gso.yaml"
s = open(p).read()
rep = [
 ("  horizontal_speed_range: [0.0, 0.0]\n",
  "  # A dropped object keeps a little horizontal velocity -- the mentor's own\n"
  "  # free_fall config uses [0.03, 0.12]; matching it keeps the bounce from\n"
  "  # being a mathematically perfect vertical drop.\n"
  "  horizontal_speed_range: [0.03, 0.10]\n"),
 ("  drop_height_absolute_range: [1.60, 2.40]\n",
  "  # Proven scale: the mentor's free_fall.yaml uses [0.45, 1.20].  A 2.4 m drop\n"
  "  # was measured to drift 0.40 m after the bounce and leave the placement\n"
  "  # rectangle (outside_surface_bounds).  1.10 m is a clearly visible fall that\n"
  "  # stays inside.\n"
  "  drop_height_absolute_range: [0.85, 1.20]\n"),
 ("  drop_height_object_extent_range: [8.0, 14.0]\n",
  "  drop_height_object_extent_range: [5.0, 9.0]\n"),
 ("  min_drop_height: 1.40\n", "  min_drop_height: 0.70\n"),
 ("  min_drop_distance: 1.40\n", "  min_drop_distance: 0.70\n"),
 ("  edge_margin: 0.10\n",
  "  # Wider than the mentor's 0.15: free_fall reserves no horizontal travel when\n"
  "  # sampling, so the placement margin is the only guard against post-bounce\n"
  "  # drift leaving the surface.\n"
  "  edge_margin: 0.60\n"),
]
for old, new in rep:
    if old not in s:
        print(f"  !! not found: {old.strip()}")
    s = s.replace(old, new)
open(p, "w").write(s)
print("  free_fall_gso.yaml updated")
PY

echo
echo "=== resulting free_fall config (physics/validation/surface) ==="
sed -n '/^physics:/,/^camera:/p' configs/scenarios/free_fall_gso.yaml | grep -vE '^\s*#' | sed 's/^/  /'

echo
echo "=== fast-test free_fall on all three actors ==="
for spec in "gso_down_to_earth_orchid_pot_ceramic_lime 3001" \
            "gso_ecoforms_plant_container_gp16a_coral 3002" \
            "gso_mad_gab_refresh_card_game 3003"; do
  set -- $spec
  echo "--- $1 ---"
  "$WS/tools/conda_env/bin/python" - "$1" "$2" <<'PY' 2>&1 | grep -E '^  |^SIM'
import sys, math
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
aid, seed = sys.argv[1], int(sys.argv[2])
cfg = load_run_config("configs/server.yaml", scenario="free_fall_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
scen = create_scenario(cfg); asset = am.get(aid)
ms = mm.get("replicad_apartment", require_files=True)
vs = variants_from_config(cfg)
v = next((x for x in vs if x.multiplier == 1.0), vs[0])
smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
print(f"SIM free_fall {aid}")
print(f"  VALID={rep.valid} reasons={list(rep.reasons)}")
m = rep.metrics
for k in ("drop_distance","supported_fraction","trajectory_extent_object_ratio",
          "max_post_contact_upward_speed","max_surface_penetration","collision_count"):
    if k in m: print(f"  {k} = {m[k]}")
PY
done
