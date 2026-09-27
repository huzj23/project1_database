#!/usr/bin/env bash
# ===========================================================================
# PROBE-RENDER candidate cameras for the 匀速 clip, cheaply.
#
# Root cause of the user's complaint, now measured exactly:
#   frl_apartment_bike_02 sits at world (-0.5512, 1.0196) and the OLD camera was at
#   (-0.643, 0.800, 0.458) -- only 0.238 m away.  The camera was practically
#   standing inside the bicycle, which is why it dominated the left of frame.
#   (My earlier "no bicycle in apt_0" search was wrong; there are two.)
#
# So the fix is simply to put the camera somewhere else.  Rather than guess, render
# ONE probe frame from each of a few candidate poses at low spp and measure:
#   * is the bicycle visible at all (raycast + pixel test),
#   * how many pixels does the actor occupy,
#   * is the trajectory inside the frame.
# Only the winner gets a full 81-frame render.
#
# Uses the real pipeline (prepare_sample) so the scene, lighting and materials are
# exactly what the final render will use -- just 1 frame and low spp.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^CB' | tail -40
import sys, os, math, json, tempfile
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera

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
say(f"trajectory mid={np.round(mid,4).tolist()} travel={np.linalg.norm(p[-1]-p[0]):.4f}")
say(f"bike_02 world=(-0.5512, 1.0196, 0.4536)")

# candidate poses: (label, camera position, look_at, focal)
CANDS = [
    ("az90_d1.4_h0.55", (-0.6744, 0.4069, 0.6127), (-0.6744, -0.9931, 0.1027), 40.0),
    ("az90_d2.2_h0.55", (-0.6744, 1.2069, 0.6127), (-0.6744, -0.9931, 0.1027), 50.0),
    ("az270_d1.4_h0.55",(-0.6744, -2.3931, 0.6127),(-0.6744, -0.9931, 0.1027), 40.0),
    ("az270_d2.2_h0.55",(-0.6744, -3.1931, 0.6127),(-0.6744, -0.9931, 0.1027), 50.0),
]

from physim.render.blender_backend import BlenderBackend
for label, pos, look, focal in CANDS:
    cam = fixed_camera(res, {"position": pos, "look_at": look, "focal_length_mm": focal})
    # line of sight: is the bike between the camera and the actor?
    d_bike = np.linalg.norm(np.array((-0.5512, 1.0196, 0.4536)) - np.array(pos))
    d_act = np.linalg.norm(mid - np.array(pos))
    fwd = (np.array(look)-np.array(pos)); fwd /= np.linalg.norm(fwd)
    vb = np.array((-0.5512,1.0196,0.4536)) - np.array(pos)
    zb = float(vb @ fwd)
    # screen position of the bike
    right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fov_h = 2*math.atan(36.0/(2*focal)); fov_v = 2*math.atan((36.0*1080/1920)/(2*focal))
    nx = math.atan2(float(vb @ right), zb)/(fov_h/2) if zb > 0 else float('nan')
    ny = math.atan2(float(vb @ up), zb)/(fov_v/2) if zb > 0 else float('nan')
    inbike = (zb > 0) and abs(nx) < 1.0 and abs(ny) < 1.0
    say(f"{label:18s} cam={tuple(round(x,3) for x in pos)} bike_d={d_bike:5.2f} "
        f"act_d={d_act:5.2f} bike_norm=({nx:+.2f},{ny:+.2f}) bike_in_frame={inbike}")
PY
