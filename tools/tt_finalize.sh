#!/usr/bin/env bash
# ===========================================================================
# FINALISE #5 (环形转动) and #6 (转盘上的转动), then pick verified seeds.
#
# Measured facts driving these choices:
#   * arc = omega * duration, INDEPENDENT of orbit radius.  At omega 0.45-0.60 the
#     arc was only 131.6 deg (a third of a circle) which does not read as a ring.
#   * A full turn in 5.0625 s needs omega = 2*pi/5.0625 = 1.241 rad/s.
#   * The elephant's measured throw-off threshold is ~5.85 rad/s, so 1.25 is 4.7x
#     below it -- the actor is firmly in the carried regime (slip 0.998-0.999).
#   * Elephant footprint_radius 0.134 m, disc r 0.30 m -> the rim is reached at
#     orbit r 0.166 (fraction 0.554), so 0.50-0.55 is the widest safe ring.
#
# #5 ring   : orbit 0.50-0.55 (widest ring), omega 1.20-1.30 -> ~345 deg, a full loop
# #6 spin   : orbit 0.15-0.25 (near the axis), same omega -> the disc and the actor
#             turn together on the spot; the subject is the rotation itself.
#
# Seeds are then screened, not guessed: a seed is accepted only if it validates,
# the actor stays inside the approved fixed frame on EVERY frame, and the disc
# rotation is a large fraction of a turn.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -45
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

CARRY = "configs/scenarios/turntable_carry_gso.yaml"
SPIN = "configs/scenarios/turntable_spin_gso.yaml"
# load_run_config(scenario=...) takes a scenario NAME (it builds
# configs/scenarios/<name>.yaml itself).  Passing the path produced a doubled
# "configs/scenarios/configs/scenarios/...yaml.yaml" and a FileNotFoundError.
CARRY_NAME = "turntable_carry_gso"
SPIN_NAME = "turntable_spin_gso"

def set_kv(path, key, lo, hi):
    s = open(path).read()
    s2, n = re.subn(rf"{key}:\s*\[[^\]]*\]", f"{key}: [{lo}, {hi}]", s)
    if n != 1:
        raise AssertionError(f"{path}:{key}: expected 1 substitution, got {n}")
    open(path, "w").write(s2)

# --- apply the measured final values ---
set_kv(CARRY, "angular_speed_range", 1.20, 1.30)
set_kv(CARRY, "orbit_radius_fraction_range", 0.50, 0.55)
set_kv(SPIN, "angular_speed_range", 1.20, 1.30)
set_kv(SPIN, "orbit_radius_fraction_range", 0.15, 0.25)
say("applied: carry omega 1.20-1.30 orbit 0.50-0.55 | spin omega 1.20-1.30 orbit 0.15-0.25")

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
surface = ms.surface("replicad_apartment_table_top")
asset = am.get("gso_sootheze_cold_therapy_elephant")

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

def run(cfg_name, seed):
    cfg = load_run_config("configs/server.yaml", scenario=cfg_name)
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    rep = validate_sample(res, smp, surface, cfg["validation"])
    cam = fixed_camera(res, cfg["camera"])
    p = np.asarray([s.position for s in res.trajectory])
    sp = np.asarray([s.position for s in res.support_trajectory])
    r = np.hypot(p[:,0]-sp[0,0], p[:,1]-sp[0,1])
    fmax = max(max(abs(a), abs(b)) for k in range(len(p))
               for a, b in [frame_norm(cam, p[k])])
    return dict(valid=rep.valid, reasons=list(rep.reasons),
                rmin=float(r.min()), rmax=float(r.max()),
                arc=float(rep.metrics.get("net_arc_degrees", 0)),
                disc=float(rep.metrics.get("disc_rotation_degrees", 0)),
                slip=float(rep.metrics.get("slip_ratio", 0)),
                radial=float(rep.metrics.get("net_radial_displacement", 0)),
                supp=float(rep.metrics.get("supported_fraction", 0)),
                speed=float(rep.metrics.get("max_linear_speed", 0)),
                fmax=fmax)

SEEDS = [5001, 5002, 5004, 5005, 5007, 5008, 5010, 5011, 5012, 5013]
for cfg_name, label in ((CARRY_NAME, "#5 ring"), (SPIN_NAME, "#6 spin")):
    say("")
    say(f"=== {label} ({cfg_name}) seed screen ===")
    say(f"{'seed':>6} {'valid':>5} {'arc':>7} {'disc':>7} {'orbit_r':>13} "
        f"{'slip':>6} {'supp':>5} {'vmax':>6} {'maxnorm':>7}")
    good = []
    for s in SEEDS:
        try:
            m = run(cfg_name, s)
            ok = m["valid"] and m["fmax"] < 0.90 and m["disc"] > 200.0
            tag = "  <== ACCEPT" if ok else ""
            say(f"{s:>6} {str(m['valid']):>5} {m['arc']:7.1f} {m['disc']:7.1f} "
                f"{m['rmin']:.3f}-{m['rmax']:.3f} {m['slip']:6.3f} {m['supp']:5.3f} "
                f"{m['speed']:6.3f} {m['fmax']:7.3f}{tag}")
            if not m["valid"]:
                say(f"        reasons: {m['reasons']}")
            if ok:
                good.append(s)
        except Exception as e:
            say(f"{s:>6} ERROR {type(e).__name__}: {str(e)[:80]}")
    say(f"  accepted seeds: {good[:4]}")
PY
