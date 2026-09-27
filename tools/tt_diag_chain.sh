#!/usr/bin/env bash
# Narrow down where the FileNotFoundError comes from: run the FULL chain
# (sample -> simulate -> validate -> fixed_camera) and print the complete traceback
# with the full path, not the truncated 80 chars my sweep printed.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -vE 'tensorflow|oneDNN|TF_ENABLE|AVX' | tail -40
import sys, traceback
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
from physim.camera import fixed_camera

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
surface = ms.surface("replicad_apartment_table_top")
asset = am.get("gso_sootheze_cold_therapy_elephant")
cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]

for step, fn in (
    ("sample", lambda: scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)),
):
    pass

smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
print("TT sample ok")
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
print("TT simulate ok; support_trajectory =", None if res.support_trajectory is None else len(res.support_trajectory))
try:
    rep = validate_sample(res, smp, surface, cfg["validation"])
    print("TT validate ok valid=", rep.valid, "reasons=", list(rep.reasons))
except Exception:
    print("TT VALIDATE FAILED:"); traceback.print_exc()
try:
    cam = fixed_camera(res, cfg["camera"])
    print("TT camera ok", cam.position)
except Exception:
    print("TT CAMERA FAILED:"); traceback.print_exc()
PY
