#!/usr/bin/env bash
# ===========================================================================
# Set the frictionless support for #1 and #2, then fast-test all three motions.
#
# MEASURED BASIS for friction_range [0.0, 0.0]:
#   With Coulomb friction the speed obeys v(t) = v0 - mu*g*t, so over the 5.0625 s
#   clip the relative change is mu*g*T/v0.  The validator allows 0.25, which needs
#   v0 >= mu*198.6.  At mu = 0.01 that is v0 >= 1.99 m/s and a ~10 m traverse --
#   larger than the 5.1 x 3.7 m clear rectangle, so the sample would also fail
#   outside_surface_bounds.  Measured sweep confirms it: mu 0.01 -> stops in
#   0.36 m, mu 0.02 -> 0.18 m, mu 0.05 -> 0.06 m.
#
#   mu = 0.0 gives exactly uniform motion (measured rel_change 0.0000, travel
#   1.000 m) because no in-plane force acts: Newton's first law, integrated by the
#   solver.  This is the same idealisation the mentor's own rolling config makes
#   (rolling_friction 0, spinning_friction 0) -- extended to lateral friction
#   because our convex-hull actors SLIDE where a ball would ROLL.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY'
for p, note in (
    ("configs/scenarios/rolling_gso.yaml",
     "  # Frictionless support: uniform motion by Newton's first law, integrated by\n"
     "  # the solver.  Measured: with mu=0.01 the body stops in 0.36 m (rel_change\n"
     "  # 0.999); with mu=0 it travels 1.000 m at constant speed (rel_change 0.0000).\n"
     "  # This mirrors the mentor's own rolling idealisation (rolling_friction 0,\n"
     "  # spinning_friction 0); our actors slide where a ball would roll.\n"),
    ("configs/scenarios/constant_force_gso.yaml",
     "  # Frictionless support so the applied force F = m*a is not opposed by contact\n"
     "  # friction.  Same reasoning and same measurement as rolling_gso.yaml.\n"),
):
    s = open(p).read()
    s = s.replace("  friction_range: [0.05, 0.08]\n", note + "  friction_range: [0.0, 0.0]\n")
    open(p, "w").write(s)
    print(f"  {p} -> frictionless")
PY

echo
echo "=== fast-test all three motions (physics only, no rendering) ==="
for spec in "rolling_gso gso_whey_protein_vanilla 1001" \
            "constant_force_gso gso_room_essentials_fabric_cube_lavender 2001" \
            "free_fall_gso gso_down_to_earth_orchid_pot_ceramic_lime 3001"; do
  set -- $spec
  echo "--- $1 / $2 ---"
  "$WS/tools/conda_env/bin/python" - "$1" "$2" "$3" <<'PY' 2>&1 | grep -E '^  |^SIM'
import sys, math
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
sf, aid, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
cfg = load_run_config("configs/server.yaml", scenario=sf)
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
scen = create_scenario(cfg); asset = am.get(aid)
ms = mm.get("replicad_apartment", require_files=True)
vs = variants_from_config(cfg)
v = next((x for x in vs if x.multiplier == 1.0), vs[0])
smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
sp = [math.hypot(s.linear_velocity[0], s.linear_velocity[1]) for s in res.trajectory]
print(f"SIM {cfg['scenario']} {aid}")
print(f"  v0={sp[0]:.4f} v_end={sp[-1]:.4f}  VALID={rep.valid} reasons={list(rep.reasons)}")
m = rep.metrics
for k in ("travel_distance","supported_fraction","max_speed_relative_change",
          "trajectory_extent_object_ratio","acceleration_relative_std",
          "drop_distance","max_post_contact_upward_speed","max_surface_penetration"):
    if k in m: print(f"  {k} = {m[k]}")
PY
done
