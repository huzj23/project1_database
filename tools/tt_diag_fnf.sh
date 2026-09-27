#!/usr/bin/env bash
# The seed screen now fails with FileNotFoundError on every seed -- the config
# edit changed the physics but the error is elsewhere.  Print the FULL message.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== current applied values ==="
grep -n 'angular_speed_range\|orbit_radius_fraction_range' configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml | sed 's/^/  /'

echo
echo "=== full traceback for one seed ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -35
import sys, traceback
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
try:
    am = AssetManager("configs/assets.yaml", "assets")
    mm = MapManager("configs/maps.yaml", am)
    ms = mm.get("replicad_apartment", require_files=True)
    asset = am.get("gso_sootheze_cold_therapy_elephant")
    cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
    print("TT sample ok")
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    print("TT simulate ok")
except Exception:
    traceback.print_exc()
PY
