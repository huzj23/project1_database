#!/usr/bin/env bash
# ===========================================================================
# Why this sweep: the previous one showed the arc is 131.6 deg NO MATTER what the
# orbit radius is.  That is expected -- arc = omega * duration -- so the ring's
# angular extent is set by OMEGA, not by the orbit radius.  131.6 deg is a third
# of a circle, which does not read as "环形转动" (circular/ring motion).
#
# A full turn in 5.0625 s needs omega = 2*pi/5.0625 = 1.241 rad/s.  The measured
# throw-off threshold for the elephant is ~5.85 rad/s (below it slip stays 1.00),
# so there is ample headroom.  Sweep omega to find the largest full-ring speed
# that still passes validation and keeps the actor inside the fixed frame.
#
# Orbit band is pinned at the measured-best (0.50, 0.55) so only omega varies.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import sys, math, re, traceback
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
PATH = "configs/scenarios/turntable_carry_gso.yaml"

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
surface = ms.surface("replicad_apartment_table_top")
asset = am.get("gso_sootheze_cold_therapy_elephant")

def set_kv(key, lo, hi):
    s = open(PATH).read()
    s2 = re.sub(rf"{key}:\s*\[[^\]]*\]", f"{key}: [{lo}, {hi}]", s)
    assert s2 != s, f"{key} not found"
    open(PATH, "w").write(s2)

def frame_norm(cam, pt):
    fwd = np.asarray(cam.look_at) - np.asarray(cam.position); fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fov_h = 2*math.atan(36.0/(2*cam.focal_length_mm))
    fov_v = 2*math.atan((36.0*(1080/1920))/(2*cam.focal_length_mm))
    d = np.asarray(pt) - np.asarray(cam.position)
    z = float(d @ fwd)
    return (math.atan2(float(d@right), z)/(fov_h/2),
            math.atan2(float(d@up), z)/(fov_v/2))

def run(seed):
    cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, surface, cfg["validation"])
    cam = fixed_camera(res, cfg["camera"])
    p = np.asarray([s.position for s in res.trajectory])
    sp = np.asarray([s.position for s in res.support_trajectory])
    r = np.hypot(p[:,0]-sp[0,0], p[:,1]-sp[0,1])
    # worst-case in-frame norm over EVERY frame, not just 3
    fmax = 0.0
    for k in range(len(p)):
        a, b = frame_norm(cam, p[k])
        fmax = max(fmax, abs(a), abs(b))
    return dict(valid=rep.valid, reasons=list(rep.reasons),
                rmin=float(r.min()), rmax=float(r.max()),
                arc=float(rep.metrics.get("net_arc_degrees", 0)),
                disc=float(rep.metrics.get("disc_rotation_degrees", 0)),
                slip=float(rep.metrics.get("slip_ratio", 0)),
                radial=float(rep.metrics.get("net_radial_displacement", 0)),
                supp=float(rep.metrics.get("supported_fraction", 0)),
                over=float(rep.metrics.get("max_overhang", 0) or 0),
                speed=float(rep.metrics.get("max_linear_speed", 0)),
                fmax=fmax)

set_kv("orbit_radius_fraction_range", 0.50, 0.55)
say(f"{'omega':>13} {'valid':>5} {'arc':>7} {'disc':>7} {'orbit_r':>13} "
    f"{'slip':>6} {'supp':>5} {'over':>7} {'vmax':>6} {'maxnorm':>7}")
for lo, hi in ((0.45,0.60),(0.90,1.00),(1.20,1.30),(1.55,1.65),(1.90,2.00),(2.40,2.60)):
    set_kv("angular_speed_range", lo, hi)
    try:
        m = run(5001)
        flag = "" if m["fmax"] < 0.92 else "  <-- OUT OF FRAME"
        say(f"{lo:.2f}-{hi:.2f} {str(m['valid']):>5} {m['arc']:7.1f} {m['disc']:7.1f} "
            f"{m['rmin']:.3f}-{m['rmax']:.3f} {m['slip']:6.3f} {m['supp']:5.3f} "
            f"{m['over']:7.4f} {m['speed']:6.3f} {m['fmax']:7.3f}{flag}")
        if not m["valid"]:
            say(f"    reasons: {m['reasons']}")
    except Exception as e:
        say(f"{lo:.2f}-{hi:.2f} ERROR {type(e).__name__}: {str(e)[:90]}")
PY
