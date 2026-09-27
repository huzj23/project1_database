#!/usr/bin/env bash
# ===========================================================================
# Sweep the knobs that could explain the roll DECELERATION.
#
# Measured baseline (seed 1001): slip ratio 1.0000 at t=0 (perfect rolling) but
# speed 0.135 -> 0.0025 m/s over 5.06 s, i.e. it stops.  Hypotheses:
#   H1 the convex hull is a POLYGON, so each facet-edge landing is an inelastic
#      impact that removes energy (geometric rolling resistance)
#   H2 restitution makes those impacts bouncy and lossy
#   H3 the initial spin is over-driven and the resulting slip brakes it
#   H4 the diagonal-inertia approximation is wrong for a rolling can
#
# For each case this reports travel, speed ratio, slip ratio and VALID, so the
# mechanism is identified by data rather than by argument.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, json, math, copy
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1001
asset_id = "gso_whey_protein_vanilla"
base_cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
asset = am.get(asset_id)
ms = mm.get("replicad_apartment", require_files=True)

CASES = [
    ("baseline",                {}),
    ("restit0",                 {"physics": {"restitution_range": [0.0, 0.0]}}),
    ("restit0+mu0.9",           {"physics": {"restitution_range": [0.0, 0.0],
                                             "friction_range": [0.9, 0.9]}}),
    ("restit0+mu0.9+om0.7",     {"physics": {"restitution_range": [0.0, 0.0],
                                             "friction_range": [0.9, 0.9]},
                                 "_omega_scale": 0.7}),
    ("restit0+speed2",          {"physics": {"restitution_range": [0.0, 0.0],
                                             "travel_object_extent_range": [8.0, 14.0]}}),
    ("restit0+speed3",          {"physics": {"restitution_range": [0.0, 0.0],
                                             "travel_object_extent_range": [12.0, 21.0]}}),
    ("restit0+speed4",          {"physics": {"restitution_range": [0.0, 0.0],
                                             "travel_object_extent_range": [16.0, 28.0]}}),
]

def run_case(label, over):
    cfg = copy.deepcopy(base_cfg)
    omega_scale = over.pop("_omega_scale", 1.0)
    for k, v in over.items():
        if isinstance(v, dict):
            cfg[k] = {**cfg.get(k, {}), **v}
        else:
            cfg[k] = v
    scen = create_scenario(cfg)
    v = next((x for x in variants_from_config(cfg) if x.multiplier == 1.0),
             variants_from_config(cfg)[0])
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    if omega_scale != 1.0:
        smp = type(smp)(**{**smp.to_dict(),
                           "angular_velocity": tuple(x*omega_scale for x in smp.angular_velocity)})
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    pos = np.asarray([s.position for s in res.trajectory], float)
    vel = np.asarray([s.linear_velocity for s in res.trajectory], float)
    om = np.asarray([s.angular_velocity for s in res.trajectory], float)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    d = vel[0, :2] / max(np.linalg.norm(vel[0, :2]), 1e-12)
    ax = np.array([-d[1], d[0], 0.0])
    oa = om @ ax
    vr = sp / smp.support_height
    mid = slice(len(sp)//4, 3*len(sp)//4)
    slip_mid = float(np.nanmean(np.where(vr > 1e-9, oa/vr, np.nan)[mid]))
    travel = float(np.linalg.norm(pos[-1]-pos[0]))
    print(f"SW {label:22s} mu={smp.friction:.2f} rest={smp.restitution:.3f} "
          f"v0={sp[0]:.4f} v_end={sp[-1]:.4f} travel={travel:.4f} "
          f"relchg={rep.metrics.get('max_speed_relative_change'):.4f} "
          f"slip_mid={slip_mid:.3f} VALID={rep.valid} {list(rep.reasons)}")
    return rep.valid

print("SW ---- rolling deceleration sweep ----")
for label, over in CASES:
    try:
        run_case(label, dict(over))
    except Exception as e:
        print(f"SW {label:22s} ERROR {type(e).__name__}: {str(e)[:130]}")
print("SW DONE")
PY
echo "RC SWEEP DONE"
