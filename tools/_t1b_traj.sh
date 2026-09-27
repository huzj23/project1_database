#!/usr/bin/env bash
# ===========================================================================
# Dump the ACTUAL rolling trajectories (all three speed variants, seed 1001)
# to JSON so the camera search can be done against the real motion rather than
# a guessed line.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/tmp/t1b_traj"
mkdir -p "$OUT"

"$WS/tools/conda_env/bin/python" - "$OUT" <<'PY'
import sys, json, os
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

OUT = sys.argv[1]
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
asset = am.get("gso_whey_protein_vanilla")
ms = mm.get("replicad_apartment", require_files=True)
scen = create_scenario(cfg)
surf = ms.surface("replicad_apartment_floor_pinned")

data = {"surface_position": list(surf.position),
        "surface_bounds_xy": list(surf.bounds_xy),
        "variants": {}}
for v in variants_from_config(cfg):
    smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, surf, cfg["validation"])
    pos = [list(map(float, s.position)) for s in res.trajectory]
    data["variants"][v.variant_id] = {
        "multiplier": float(v.multiplier),
        "positions": pos,
        "support_height": float(smp.support_height),
        "radius": float(smp.radius),
        "quaternion0": list(map(float, smp.initial_quaternion)),
        "valid": bool(rep.valid),
        "reasons": list(rep.reasons),
        "travel": float(np.linalg.norm(np.asarray(pos[-1]) - np.asarray(pos[0]))),
    }
    p = np.asarray(pos)
    print(f"TJ {v.variant_id:5s} n={len(pos)} travel={data['variants'][v.variant_id]['travel']:.4f} "
          f"x=[{p[:,0].min():.4f},{p[:,0].max():.4f}] y=[{p[:,1].min():.4f},{p[:,1].max():.4f}] "
          f"z=[{p[:,2].min():.4f},{p[:,2].max():.4f}] valid={rep.valid}")

allpos = np.vstack([np.asarray(v["positions"]) for v in data["variants"].values()])
data["all_bounds"] = {"min": allpos.min(axis=0).tolist(),
                      "max": allpos.max(axis=0).tolist(),
                      "center": ((allpos.min(axis=0)+allpos.max(axis=0))/2).tolist()}
print(f"TJ all x=[{allpos[:,0].min():.4f},{allpos[:,0].max():.4f}] "
      f"y=[{allpos[:,1].min():.4f},{allpos[:,1].max():.4f}] "
      f"z=[{allpos[:,2].min():.4f},{allpos[:,2].max():.4f}]")
print(f"TJ center={np.round(data['all_bounds']['center'],4).tolist()}")
with open(os.path.join(OUT, "traj.json"), "w") as fh:
    json.dump(data, fh, indent=1)
print(f"TJ wrote {os.path.join(OUT,'traj.json')}")
PY
echo "RC TRAJ DUMP DONE"
