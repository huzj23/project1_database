#!/usr/bin/env bash
# Install + fast-test the projectile config.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

cp "$WS/tools/cfg_projectile_gso.yaml" configs/scenarios/projectile_gso.yaml
sed -i 's/\r$//' configs/scenarios/projectile_gso.yaml
echo "installed configs/scenarios/projectile_gso.yaml"

echo
echo "=== fast-test projectile (3 actors) ==="
"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^SIM|^  '
import sys
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

cfg = load_run_config("configs/server.yaml", scenario="projectile_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
npass = 0
cases = (("gso_mad_gab_refresh_card_game", 4001),
         ("gso_ecoforms_plant_container_gp16a_coral", 4002),
         ("gso_down_to_earth_orchid_pot_ceramic_lime", 4003))
for aid, seed in cases:
    scen = create_scenario(cfg); asset = am.get(aid)
    vs = variants_from_config(cfg)
    v = next((x for x in vs if x.multiplier == 1.0), vs[0])
    try:
        smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
        res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
        rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
        npass += rep.valid
        pos = np.array([s.position for s in res.trajectory])
        hv = float(np.hypot(smp.linear_velocity[0], smp.linear_velocity[1]))
        print(f"SIM {aid.replace('gso_','')} VALID={rep.valid} {list(rep.reasons)}")
        print(f"  v_horiz={hv:.3f} drop={rep.metrics.get('drop_distance'):.3f} "
              f"dx={pos[-1,0]-pos[0,0]:+.3f} dy={pos[-1,1]-pos[0,1]:+.3f} "
              f"x_range={pos[:,0].ptp():.3f} y_range={pos[:,1].ptp():.3f}")
        print(f"  sup={rep.metrics.get('supported_fraction'):.3f} "
              f"extent={rep.metrics.get('trajectory_extent_object_ratio'):.2f} "
              f"pen={rep.metrics.get('max_surface_penetration'):.4f}")
    except Exception as e:
        print(f"SIM {aid} ERROR {type(e).__name__}: {e}")
print(f"SIM TOTAL {npass}/3 PASS")
PY
