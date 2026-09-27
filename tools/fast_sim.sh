#!/usr/bin/env bash
# ===========================================================================
# FAST physics-only test harness: simulate + validate WITHOUT rendering.
#
# Rendering is ~15 s/frame (20 min per 81-frame clip).  Physics is ~1 s.  Tuning
# contact parameters against the real validator therefore needs a harness that
# skips Blender entirely -- otherwise every parameter iteration costs 20 minutes.
#
# This calls the same Scenario, PhysicsBackend and validator the pipeline uses, so
# a PASS here means the same sample will pass the real run.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, json, math, importlib
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

scenario_file = sys.argv[1]
asset_id = sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

cfg = load_run_config("configs/server.yaml", scenario=scenario_file)
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
scen = create_scenario(cfg)
asset = am.get(asset_id)
ms = mm.get("replicad_apartment", require_files=True)
v = next((x for x in variants_from_config(cfg) if x.multiplier == 1.0),
         variants_from_config(cfg)[0])
smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)

backend = PyBulletBackend("third_party/phyco-sim")
res = backend.simulate(smp, ms, asset)
surf = ms.surface(smp.surface_id)
rep = validate_sample(res, smp, surf, cfg["validation"])

sp = [math.hypot(s.linear_velocity[0], s.linear_velocity[1]) for s in res.trajectory]
zs = [s.position[2] for s in res.trajectory]
print(f"SIM scenario={cfg['scenario']} asset={asset_id} seed={seed}")
print(f"  frames={len(res.trajectory)} collisions={len(res.collisions)}")
print(f"  v0={sp[0]:.4f} v_mid={sp[len(sp)//2]:.4f} v_end={sp[-1]:.4f}")
print(f"  z0={zs[0]:.5f} z_end={zs[-1]:.5f}")
print(f"  VALID={rep.valid} reasons={list(rep.reasons)}")
m = rep.metrics
for k in ("travel_distance", "supported_fraction", "max_speed_relative_change",
          "max_linear_speed", "trajectory_extent_object_ratio",
          "acceleration_relative_std", "measured_force_direction_acceleration",
          "drop_distance", "max_post_contact_upward_speed",
          "max_surface_penetration"):
    if k in m:
        print(f"  {k} = {m[k]}")
PY
