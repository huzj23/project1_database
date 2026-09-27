#!/usr/bin/env bash
# ===========================================================================
# Tune the damping band so the x1.5 variant stays a DECAY rather than a stop.
#
# Measured: damping_range [0.25, 0.45] gives k up to 0.597 for x1.5, whose decay
# ratio over 5.06 s is exp(-0.597*5.06) = 0.049 -- but the solver measured 0.011,
# below the 0.03 floor, so validate_damping reported over_damped.
#
# The decay itself is correct (v0 0.621 -> 0.0066, monotonic, travel 0.676 m); the
# coefficient is simply large enough that the tail is nearly flat by the end.
# Lowering the band keeps all three variants clearly in the decaying regime while
# still making x1.5 visibly faster to settle than x1.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY'
p = "configs/scenarios/damping_gso.yaml"
s = open(p).read()
s = s.replace(
"  damping_range: [0.25, 0.45]\n",
"  # x1.5 multiplies this by 1.5, so the band tops out at k=0.45 -> a decay ratio\n"
"  # of exp(-0.45*5.0625) = 0.10, comfortably above the over_damped floor.  A higher\n"
"  # band (measured k=0.597) drove the tail to 0.011 and tripped the guard.\n"
"  damping_range: [0.18, 0.30]\n")
open(p, "w").write(s)
print("  damping_range -> [0.18, 0.30]")
PY

echo
echo "=== re-test all six damping samples ==="
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

cfg = load_run_config("configs/server.yaml", scenario="damping_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
npass = 0
for aid, seed in (("gso_whey_protein_vanilla", 7001),
                  ("gso_room_essentials_fabric_cube_lavender", 7002)):
    for mult in (1.0, 0.5, 1.5):
        scen = create_scenario(cfg); asset = am.get(aid)
        vs = variants_from_config(cfg)
        v = next((x for x in vs if x.multiplier == mult), vs[0])
        smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
        res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
        rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
        npass += rep.valid
        sp = np.linalg.norm([s.linear_velocity[:2] for s in res.trajectory], axis=1)
        print(f"SIM {aid.replace('gso_','')} x{mult} k={smp.linear_damping:.3f} "
              f"VALID={rep.valid} {list(rep.reasons)}")
        print(f"  v0={sp[0]:.4f} v_end={sp[-1]:.4f} decay={rep.metrics.get('damping_decay_ratio'):.4f} "
              f"exp={rep.metrics.get('damping_expected_ratio'):.4f} "
              f"travel={rep.metrics.get('travel_distance'):.3f} sup={rep.metrics.get('supported_fraction'):.3f}")
print(f"SIM TOTAL {npass}/6 PASS")
PY

echo
echo "=== T1 render progress ==="
bash "$WS/tools/mon_t1.sh" 2>&1 | head -20
