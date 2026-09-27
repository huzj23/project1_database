#!/usr/bin/env bash
# ===========================================================================
# FAST PROBE for the approved fixed camera + elephant on the disc.
#
# Rendering is ~15-23 s/frame, so 81 frames is ~20-30 min.  Before paying that,
# answer the three questions that would waste the render:
#   1. is the elephant actually ON the disc (resting z, inside the rim)?
#   2. does the approved camera SEE it (line of sight clear, healthy pixel count)?
#   3. is the elephant inside the frame at BOTH the first and last frame?
# Plus render a few probe frames only.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^TT'
import sys, math, json
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
from physim.camera import fixed_camera

def say(*a): print("TT", *a, flush=True)

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
surface = ms.surface("replicad_apartment_table_top")
say(f"table_top pos={surface.position} bounds={surface.bounds_xy}")

for name, seed in (("turntable_carry_gso", 5001), ("turntable_spin_gso", 6002)):
    cfg = load_run_config("configs/server.yaml", scenario=name)
    asset = am.get("gso_sootheze_cold_therapy_elephant")
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, surface, cfg["validation"])
    p = np.asarray([s.position for s in res.trajectory])
    # disc centre = mean of the actor's circular path (the orbit centre)
    cx, cy = p[:, 0].mean(), p[:, 1].mean()
    r = np.hypot(p[:, 0] - cx, p[:, 1] - cy)
    say(f"{name} seed={seed} valid={rep.valid} reasons={list(rep.reasons)}")
    say(f"  actor z: min={p[:,2].min():.5f} max={p[:,2].max():.5f}  "
        f"expected={surface.position[2] + 0.011 + asset.support_height:.5f}")
    say(f"  orbit r: min={r.min():.4f} max={r.max():.4f} (disc r=0.30)  "
        f"travel={np.linalg.norm(p[-1]-p[0]):.4f}")
    for k, val in sorted(rep.metrics.items()):
        if any(t in k for t in ("arc", "slip", "radial", "supported", "disc_rotation", "overhang")):
            say(f"  metric {k} = {val}")
    if res.support_trajectory:
        sp = np.asarray([s.position for s in res.support_trajectory])
        say(f"  disc: n={len(sp)} z={sp[:,2].min():.5f}..{sp[:,2].max():.5f} "
            f"xy_drift={np.hypot(sp[:,0]-sp[0,0], sp[:,1]-sp[0,1]).max():.6f}")

    # --- the approved camera ---
    cam = fixed_camera(res, cfg["camera"])
    say(f"  camera pos={tuple(round(x,4) for x in cam.position)} "
        f"look={tuple(round(x,4) for x in cam.look_at)} focal={cam.focal_length_mm}")

    # is the actor inside the frustum at the first and last frame?
    fov_h = 2*math.atan(36.0/(2*cam.focal_length_mm))
    fov_v = 2*math.atan((36.0*(1080/1920))/(2*cam.focal_length_mm))
    fwd = np.asarray(cam.look_at) - np.asarray(cam.position); fwd /= np.linalg.norm(fwd)
    up_w = np.array([0,0,1.0])
    right = np.cross(fwd, up_w); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    for label, pt in (("first", p[0]), ("last", p[-1])):
        d = np.asarray(pt) - np.asarray(cam.position)
        z = float(d @ fwd)
        ax = math.atan2(float(d @ right), z)
        ay = math.atan2(float(d @ up), z)
        fx = ax/(fov_h/2); fy = ay/(fov_v/2)
        say(f"  frame[{label}]: depth={z:.3f} m  norm_x={fx:+.3f} norm_y={fy:+.3f} "
            f"-> {'INSIDE' if abs(fx)<0.92 and abs(fy)<0.92 else 'NEAR/OUTSIDE EDGE'}")
PY
