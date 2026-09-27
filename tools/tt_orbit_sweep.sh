#!/usr/bin/env bash
# ===========================================================================
# TUNE #5 (环形转动) so the ring actually READS as a ring with the elephant.
#
# Measured problem: with orbit_radius_fraction_range [0.35,0.50] the actor orbits
# at r = 0.028-0.131 m.  The elephant is 0.269 x 0.222 x 0.210 m with a footprint
# radius near 0.11 m, so an orbit of r ~ 0.13 traces a circle (diameter 0.26 m)
# barely larger than the toy itself -- it looks like it is spinning in place, not
# travelling around a ring.
#
# A ring reads clearly when the orbit diameter is a few times the footprint.  The
# disc is r = 0.30 m, so the orbit can grow until the actor overhangs the rim
# (the validator allows 0.02 m overhang).  Sweep it and pick from measurement.
#
# Also: with the camera now FIXED, occlusion is no longer seed-dependent in the
# way it was (the pose no longer derives from the trajectory), but the actor's
# placement still varies with the seed, so every candidate seed is checked for
# line of sight and for being inside the frame at BOTH ends of the clip.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

cp configs/scenarios/turntable_carry_gso.yaml /tmp/carry.bak
cp configs/scenarios/turntable_spin_gso.yaml /tmp/spin.bak

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^TT'
import sys, math, re
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
ELEPHANT = "gso_sootheze_cold_therapy_elephant"
asset = am.get(ELEPHANT)
say(f"elephant footprint_radius={asset.footprint_radius:.5f} "
    f"support_height={asset.support_height:.5f} bounding_radius={asset.bounding_radius:.5f}")
say(f"disc r=0.30 -> max orbit without overhang = {0.30 - asset.footprint_radius:.4f} m "
    f"(fraction {(0.30-asset.footprint_radius)/0.30:.3f})")

def set_orbit(path, lo, hi):
    s = open(path).read()
    s2 = re.sub(r"orbit_radius_fraction_range:\s*\[[^\]]*\]",
                f"orbit_radius_fraction_range: [{lo}, {hi}]", s)
    assert s2 != s, "orbit key not found"
    open(path, "w").write(s2)

def frame_norm(cam, pt):
    fwd = np.asarray(cam.look_at) - np.asarray(cam.position); fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fov_h = 2*math.atan(36.0/(2*cam.focal_length_mm))
    fov_v = 2*math.atan((36.0*(1080/1920))/(2*cam.focal_length_mm))
    d = np.asarray(pt) - np.asarray(cam.position)
    z = float(d @ fwd)
    return (math.atan2(float(d@right), z)/(fov_h/2), math.atan2(float(d@up), z)/(fov_v/2), z)

def run(cfg_name, seed):
    cfg = load_run_config("configs/server.yaml", scenario=cfg_name)
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, surface, cfg["validation"])
    cam = fixed_camera(res, cfg["camera"])
    p = np.asarray([s.position for s in res.trajectory])
    cx, cy = p[:,0].mean(), p[:,1].mean()
    r = np.hypot(p[:,0]-cx, p[:,1]-cy)
    fx0, fy0, z0 = frame_norm(cam, p[0]); fx1, fy1, z1 = frame_norm(cam, p[-1])
    inside = max(abs(fx0),abs(fy0),abs(fx1),abs(fy1)) < 0.92
    return dict(valid=rep.valid, reasons=list(rep.reasons),
                rmin=float(r.min()), rmax=float(r.max()),
                travel=float(np.linalg.norm(p[-1]-p[0])),
                arc=float(rep.metrics.get("net_arc_degrees", 0)),
                slip=float(rep.metrics.get("slip_ratio", 0)),
                radial=float(rep.metrics.get("net_radial_displacement", 0)),
                supp=float(rep.metrics.get("supported_fraction", 0)),
                overhang=float(rep.metrics.get("max_overhang", 0)),
                inside=inside, depth=(z0, z1),
                fmax=max(abs(fx0),abs(fy0),abs(fx1),abs(fy1)))

say("")
say("=== CARRY orbit sweep (actor=elephant, seed 5001) ===")
say(f"{'lo-hi':>10} {'valid':>5} {'orbit_r':>14} {'travel':>7} {'arc':>7} {'slip':>6} {'radial':>8} {'supp':>5} {'inframe':>7} {'maxnorm':>7}")
for lo, hi in ((0.35,0.50),(0.45,0.55),(0.50,0.60),(0.55,0.65),(0.60,0.68)):
    set_orbit("configs/scenarios/turntable_carry_gso.yaml", lo, hi)
    try:
        m = run("turntable_carry_gso", 5001)
        say(f"{lo:.2f}-{hi:.2f} {str(m['valid']):>5} "
            f"{m['rmin']:.3f}-{m['rmax']:.3f} {m['travel']:7.4f} {m['arc']:7.1f} "
            f"{m['slip']:6.3f} {m['radial']:8.5f} {m['supp']:5.3f} "
            f"{str(m['inside']):>7} {m['fmax']:7.3f}")
        if not m["valid"]:
            say(f"    reasons: {m['reasons']}")
    except Exception as e:
        say(f"{lo:.2f}-{hi:.2f} ERROR {type(e).__name__}: {str(e)[:80]}")
PY
