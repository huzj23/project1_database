#!/usr/bin/env bash
# ===========================================================================
# Scenario-level sweep of the physics rate, with the REAL asset, the REAL
# scanned floor and the REAL validator.
#
# Rationale: Bullet's contact solver injects energy into rolling contact at
# coarse timesteps (measured: +37% total mechanical energy at 240 Hz for an
# ideal cylinder on an ideal plane, converging to +3% at 1920 Hz).  This finds
# the coarsest rate at which the scenario still passes its own constant-velocity
# gate, so the clip is as cheap as it can honestly be.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, copy
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1001
base = load_run_config("configs/server.yaml", scenario="rolling_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
asset = am.get("gso_whey_protein_vanilla")
ms = mm.get("replicad_apartment", require_files=True)

def run(fps, tol, seed=seed):
    cfg = copy.deepcopy(base)
    cfg["timing"] = {**cfg["timing"], "physics_fps": fps}
    cfg["validation"] = {**cfg["validation"], "max_speed_relative_change": tol}
    scen = create_scenario(cfg)
    v = next(x for x in variants_from_config(cfg) if x.multiplier == 1.0)
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    pos = np.asarray([s.position for s in res.trajectory], float)
    vel = np.asarray([s.linear_velocity for s in res.trajectory], float)
    om = np.asarray([s.angular_velocity for s in res.trajectory], float)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    d = vel[0, :2]/max(np.linalg.norm(vel[0, :2]), 1e-12)
    oa = om @ np.array([-d[1], d[0], 0.0])
    vr = sp/smp.support_height
    mid = slice(len(sp)//4, 3*len(sp)//4)
    slip = float(np.nanmean(np.where(vr > 1e-9, oa/vr, np.nan)[mid]))
    print(f"FS fps={fps:5d} tol={tol:.3f} v0={sp[0]:.4f} v_end={sp[-1]:.4f} "
          f"travel={np.linalg.norm(pos[-1]-pos[0]):.4f} "
          f"relchg={rep.metrics.get('max_speed_relative_change'):.5f} "
          f"slip_mid={slip:.4f} z_err_mm={np.abs(pos[:,2]-(ms.surface(smp.surface_id).position[2]+smp.support_height)).max()*1000:.3f} "
          f"sup={rep.metrics.get('supported_fraction'):.3f} VALID={rep.valid} {list(rep.reasons)}")
    return rep.valid

print("FS ---- physics rate vs constant-velocity gate ----")
for fps in (240, 480, 960, 1920, 3840):
    try:
        run(fps, 0.25)
    except Exception as e:
        print(f"FS fps={fps:5d} ERROR {type(e).__name__}: {str(e)[:120]}")
print("FS ---- seeds at the promising rates ----")
for fps in (960, 1920):
    for s in (1001, 1002, 1003, 1004, 1005):
        try:
            run(fps, 0.25, seed=s)
        except Exception as e:
            print(f"FS fps={fps:5d} seed={s} ERROR {type(e).__name__}: {str(e)[:110]}")
print("FS DONE")
PY
echo "RC FPS SWEEP DONE"
