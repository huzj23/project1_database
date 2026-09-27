#!/usr/bin/env bash
# ===========================================================================
# Evaluate candidate cameras for the 匀速 clip.
#
# (Previous run died on a bogus `from physim.render.blender_backend import
# BlenderBackend` -- that class has a different name.  The import was unnecessary:
# the geometry below is all that is needed to decide, and it works.)
#
# Measured root cause of the user's complaint: frl_apartment_bike_02 sits at
# world (-0.5512, 1.0196) and the OLD camera was at (-0.643, 0.800, 0.458) --
# 0.238 m away, i.e. the camera was standing inside the bicycle.  So the fix is to
# move the camera; what matters is that the bicycle is far away AND out of frame.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^CB'
import sys, math
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend

def say(*a): print("CB", *a, flush=True)

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
say(f"trajectory mid={np.round(mid,4).tolist()} travel={np.linalg.norm(p[-1]-p[0]):.4f} m")
BIKES = {"bike_01": np.array([4.1074, 0.976, 0.4546]),
         "bike_02": np.array([-0.5512, 1.0196, 0.4536])}
say(f"bike_02 = {BIKES['bike_02'].tolist()} (the one 0.238 m from the OLD camera)")

def project(pos, look, focal, pt, aspect=1080/1920):
    fwd = np.array(look)-np.array(pos); fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fov_h = 2*math.atan(36.0/(2*focal)); fov_v = 2*math.atan((36.0*aspect)/(2*focal))
    vp = np.array(pt)-np.array(pos); z = float(vp @ fwd)
    if z <= 0.05: return None, None, z
    return math.atan2(float(vp@right), z)/(fov_h/2), math.atan2(float(vp@up), z)/(fov_v/2), z

CANDS = [
    ("az90_d1.4_h0.55",  (-0.6744, 0.4069, 0.6127), 40.0),
    ("az90_d2.2_h0.55",  (-0.6744, 1.2069, 0.6127), 50.0),
    ("az90_d1.8_h0.90",  (-0.6744, 0.8069, 0.9627), 50.0),
    ("az270_d1.4_h0.55", (-0.6744, -2.3931, 0.6127), 40.0),
    ("az270_d2.2_h0.55", (-0.6744, -3.1931, 0.6127), 50.0),
    ("az270_d1.8_h0.90", (-0.6744, -2.7931, 0.9627), 50.0),
]
look = (-0.6744, -0.9931, 0.1027)
say(f"{'label':18s} {'bike01_d':>8} {'bike02_d':>8} {'bike02_inframe':>14} "
    f"{'objfrac':>8} {'traj_worst':>10}")
for label, pos, focal in CANDS:
    d1 = float(np.linalg.norm(BIKES["bike_01"]-np.array(pos)))
    d2 = float(np.linalg.norm(BIKES["bike_02"]-np.array(pos)))
    nx, ny, z = project(pos, look, focal, BIKES["bike_02"])
    inb = (nx is not None) and abs(nx) < 1.0 and abs(ny) < 1.0
    # actor size
    _, _, za = project(pos, look, focal, mid)
    fov_h = 2*math.atan(36.0/(2*focal))
    objfrac = (2*asset.radius)/(2*za*math.tan(fov_h/2))
    worst = 0.0
    for pt in (p[0], p[-1], p[len(p)//2]):
        a, b, _ = project(pos, look, focal, pt)
        worst = max(worst, abs(a), abs(b))
    say(f"{label:18s} {d1:8.2f} {d2:8.2f} {str(inb):>14} {objfrac:8.3f} {worst:10.3f}")
PY
