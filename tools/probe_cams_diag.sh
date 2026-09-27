#!/usr/bin/env bash
# The candidate loop printed nothing because the `grep -E '^CB'` filter hid the
# traceback.  Re-run with NO output filter so the real error is visible.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -viE 'tensorflow|oneDNN|TF_ENABLE|AVX|^20[0-9][0-9]-' | tail -30
import sys, math, traceback
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get("gso_whey_protein_vanilla")
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
p = np.array([s.position for s in res.trajectory])
mid = (p.min(axis=0)+p.max(axis=0))/2.0
print("CB mid", np.round(mid,4).tolist())

try:
    from physim.render.blender_backend import BlenderBackend
    print("CB BlenderBackend import ok")
except Exception:
    print("CB import FAILED"); traceback.print_exc()

try:
    cam = fixed_camera(res, {"position": (-0.6744, 0.4069, 0.6127),
                             "look_at": (-0.6744, -0.9931, 0.1027),
                             "focal_length_mm": 40.0})
    print("CB fixed_camera ok", cam.position)
except Exception:
    print("CB fixed_camera FAILED"); traceback.print_exc()
PY
