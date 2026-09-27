#!/usr/bin/env bash
# ===========================================================================
# CARRY orbit sweep, corrected.
#
# Fixes from the failed run: AssetSpec exposes `radius` / `support_height`, NOT
# `footprint_radius` (that lives on `collision`).  And the stderr filter that hid
# the crash is gone -- errors are printed, not swallowed.
#
# Why sweep at all: with orbit_radius_fraction [0.35,0.50] the actor orbits at
# r ~ 0.13 m, which for a 0.268 m-wide elephant looks like spinning in place
# rather than travelling around a ring.  Measured geometry:
#     elephant footprint_radius = 0.133966, disc r = 0.30
#     => the outer edge reaches the rim at orbit r = 0.166  (fraction 0.554)
# so the usable band tops out near 0.55 and the validator allows 0.02 m overhang.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

cp configs/scenarios/turntable_carry_gso.yaml "$WS/tmp/carry_orig.yaml"

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -40
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
fr = asset.collision.footprint_radius
say(f"elephant size={asset.size} fp_r={fr:.5f} sh={asset.support_height:.5f}")
say(f"disc r=0.30 -> rim contact at orbit r={0.30-fr:.4f} (fraction {(0.30-fr)/0.30:.3f})")

def set_orbit(lo, hi):
    s = open(PATH).read()
    s2 = re.sub(r"orbit_radius_fraction_range:\s*\[[^\]]*\]",
                f"orbit_radius_fraction_range: [{lo}, {hi}]", s)
    assert s2 != s, "orbit key not found"
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
            math.atan2(float(d@up), z)/(fov_v/2), z)

def run(seed):
    cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, surface, cfg["validation"])
    cam = fixed_camera(res, cfg["camera"])
    p = np.asarray([s.position for s in res.trajectory])
    # orbit centre = the disc axis = disc position (from support trajectory)
    sp = np.asarray([s.position for s in res.support_trajectory]) if res.support_trajectory else None
    cx, cy = (sp[0,0], sp[0,1]) if sp is not None else (p[:,0].mean(), p[:,1].mean())
    r = np.hypot(p[:,0]-cx, p[:,1]-cy)
    ns = [frame_norm(cam, p[k]) for k in (0, len(p)//2, len(p)-1)]
    fmax = max(max(abs(a), abs(b)) for a, b, _ in ns)
    return dict(valid=rep.valid, reasons=list(rep.reasons),
                rmin=float(r.min()), rmax=float(r.max()),
                travel=float(np.linalg.norm(p[-1]-p[0])),
                arc=float(rep.metrics.get("net_arc_degrees", 0)),
                slip=float(rep.metrics.get("slip_ratio", 0)),
                radial=float(rep.metrics.get("net_radial_displacement", 0)),
                supp=float(rep.metrics.get("supported_fraction", 0)),
                over=float(rep.metrics.get("max_overhang", 0) or 0),
                fmax=fmax, z=(p[:,2].min(), p[:,2].max()))

say("")
say(f"{'lo-hi':>10} {'valid':>5} {'orbit_r':>13} {'travel':>7} {'arc':>6} "
    f"{'slip':>6} {'radial':>8} {'supp':>5} {'over':>7} {'maxnorm':>7}")
best = None
for lo, hi in ((0.35,0.50),(0.42,0.50),(0.45,0.52),(0.48,0.55),(0.50,0.55)):
    set_orbit(lo, hi)
    try:
        m = run(5001)
        say(f"{lo:.2f}-{hi:.2f} {str(m['valid']):>5} "
            f"{m['rmin']:.3f}-{m['rmax']:.3f} {m['travel']:7.4f} {m['arc']:6.1f} "
            f"{m['slip']:6.3f} {m['radial']:8.5f} {m['supp']:5.3f} {m['over']:7.4f} {m['fmax']:7.3f}")
        if not m["valid"]:
            say(f"    reasons: {m['reasons']}")
        if m["valid"] and m["fmax"] < 0.92:
            if best is None or m["rmax"] > best[1]["rmax"]:
                best = ((lo, hi), m)
    except Exception:
        say(f"{lo:.2f}-{hi:.2f} ERROR"); traceback.print_exc()

if best:
    say(f"BEST orbit band = {best[0]}  rmax={best[1]['rmax']:.4f} "
        f"arc={best[1]['arc']:.1f} travel={best[1]['travel']:.4f}")
PY
