#!/usr/bin/env bash
# Install the damping config and fast-test it (physics only).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

cp "$WS/tools/cfg_damping_gso.yaml" configs/scenarios/damping_gso.yaml
sed -i 's/\r$//' configs/scenarios/damping_gso.yaml
echo "installed configs/scenarios/damping_gso.yaml"

echo
echo "=== fast-test damping ==="
"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^  |^SIM|^DECAY'
import sys, math
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

cfg = load_run_config("configs/server.yaml", scenario="damping_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)

for aid, seed in (("gso_whey_protein_vanilla", 7001),
                  ("gso_room_essentials_fabric_cube_lavender", 7002)):
    for mult in (1.0, 0.5, 1.5):
        scen = create_scenario(cfg)
        asset = am.get(aid)
        vs = variants_from_config(cfg)
        v = next((x for x in vs if x.multiplier == mult), vs[0])
        try:
            smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
            res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
            rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
            sp = np.linalg.norm([s.linear_velocity[:2] for s in res.trajectory], axis=1)
            print(f"SIM {aid.replace('gso_','')} x{mult} k={smp.linear_damping:.3f}")
            print(f"  VALID={rep.valid} reasons={list(rep.reasons)}")
            print(f"  v0={sp[0]:.4f} v_end={sp[-1]:.4f} decay={rep.metrics.get('damping_decay_ratio'):.4f} "
                  f"expected={rep.metrics.get('damping_expected_ratio'):.4f} err={rep.metrics.get('damping_ratio_error'):.4f}")
            print(f"  travel={rep.metrics.get('travel_distance'):.3f} sup={rep.metrics.get('supported_fraction'):.3f}")
            print(f"DECAY {' '.join('%.4f' % sp[i] for i in range(0, len(sp), 16))}")
        except Exception as e:
            print(f"SIM {aid} x{mult} ERROR {e}")
PY
