#!/usr/bin/env bash
# ===========================================================================
# PREFLIGHT the 4 turntable clips at the new pulled-back camera (k=1.5) BEFORE
# rendering, because a framing rejection costs a full ~20-minute render.
#
# Runs the real pipeline path sample -> simulate -> validate -> CAMERA for all four
# (seed, scenario) pairs and reports the projected on-screen extent, so nothing is
# launched that the camera step would reject.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -22
import sys, math
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
from physim.camera import fixed_camera
from physim.pipeline import _camera_config

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)

JOBS = [("turntable_carry_gso", "turntable_carry", 5001),
        ("turntable_carry_gso", "turntable_carry", 5002),
        ("turntable_spin_gso",  "turntable_spin",  5001),
        ("turntable_spin_gso",  "turntable_spin",  5002)]
print(f"  {'scenario':16s} {'seed':>6s} {'valid':>6s} {'arc':>8s} {'r':>16s} "
      f"{'maxnorm':>8s}  reasons")
allok = True
for scen_name, folder, seed in JOBS:
    cfg = load_run_config("configs/server.yaml", scenario=scen_name)
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    asset = am.get("gso_sootheze_cold_therapy_elephant")
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    camcfg = _camera_config(cfg, ms, smp)
    cam = fixed_camera(res, camcfg)
    p = np.array([s.position for s in res.trajectory])
    st = res.support_trajectory
    sp = np.array([s.position for s in st]) if st else None
    cx, cy = (sp[0,0], sp[0,1]) if sp is not None else (p[:,0].mean(), p[:,1].mean())
    ang = np.unwrap(np.arctan2(p[:,1]-cy, p[:,0]-cx))
    arc = math.degrees(ang[-1]-ang[0])
    r = np.hypot(p[:,0]-cx, p[:,1]-cy)
    # projected extent of the actor over the clip
    fwd = np.array(cam.look_at)-np.array(cam.position); fwd/=np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0,0,1.0])); right/=np.linalg.norm(right)
    up = np.cross(right, fwd)
    fov_h = 2*math.atan(36.0/(2*cam.focal_length_mm))
    fov_v = 2*math.atan((36.0*1080/1920)/(2*cam.focal_length_mm))
    worst = 0.0
    for pt in p[::4]:
        d = pt-np.array(cam.position); z=float(d@fwd)
        worst = max(worst, abs(math.atan2(float(d@right),z)/(fov_h/2)),
                            abs(math.atan2(float(d@up),z)/(fov_v/2)))
    ok = rep.valid and worst < 1.0
    allok = allok and ok
    print(f"  {folder:16s} {seed:6d} {str(rep.valid):>6s} {arc:+7.1f}d "
          f"{r.min():.4f}-{r.max():.4f} {worst:8.3f}  {list(rep.reasons)}"
          f"{'' if ok else '  <-- PROBLEM'}")
print(f"\n  camera = {cam.position} look={cam.look_at} focal={cam.focal_length_mm}")
print(f"  ALL FOUR READY: {allok}")
PY
