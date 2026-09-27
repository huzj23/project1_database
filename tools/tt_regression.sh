#!/usr/bin/env bash
# ===========================================================================
# Turntable regression using the SAME path as preflight_full3.sh
# (create_scenario + PyBulletBackend.simulate + validate_sample).
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

"$PY" - <<'PY' 2>&1 | grep -aE '^RV|^ERROR|Error|Traceback' | sed 's/^/  /'
import sys
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config, reference_variant
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
a = am.get("special_plush_elephant")

CASES = [("turntable_carry_gso", 5001), ("turntable_carry_gso", 5002),
         ("turntable_spin_gso", 5001), ("turntable_spin_gso", 5002)]
for name, seed in CASES:
    cfg = load_run_config("configs/server.yaml", scenario=name)
    scen = create_scenario(cfg, asset_manager=am)
    ref = reference_variant(cfg)
    smp = scen.sample(seed=seed, asset=a, map_spec=ms, variant=ref)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, a)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    print(f"RV {name:20s} seed={seed} valid={rep.valid} reasons={list(rep.reasons)}")
PY

echo
echo "=== preflight (must stay 14/14) ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -2 | sed 's/^/  /'
