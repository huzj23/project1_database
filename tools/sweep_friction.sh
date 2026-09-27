#!/usr/bin/env bash
# ===========================================================================
# Diagnose the last rolling failure: non_uniform_speed.
#
# Measured: v0 = 0.135 m/s -> v_end = 0.0003 m/s with friction_range [0.05,0.08]
# and 3298 contacts.  So friction is still braking a SLIDING body.
#
# Why: the rolling scenario computes
#     angular_velocity = cross(normal, linear_velocity) / support_height
# This is the PURE-ROLLING condition for a body of radius = support_height.  Our
# actors are a can and a fabric cube: support_height is their HALF-HEIGHT, not a
# rolling radius, so the spin it requests is far too large for the actual contact.
# The contact then converts that mismatch into a braking force and the body stops.
#
# Two honest options, both solver-driven:
#   A. low friction AND no imposed spin -> the body slides at nearly constant
#      speed (a puck on a polished floor).  This is "匀速（平动）", one of the two
#      names motion #1 already carries ("滚动/平动").
#   B. keep rolling semantics for a genuinely round actor -- but we have no ball
#      with a visual (V3.3 §3.1), so B is not available tonight.
#
# Measure A: friction sweep with the spin removed, and see which mu satisfies
# max_speed_relative_change <= 0.25 over 81 frames.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' > "$WS/tmp/sweep.log" 2>&1
import sys, os, tempfile, math
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np, kubric as kb, phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
import pybullet as pbc

WS = "/data/raw/huzijian/project1_database"
ENV = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment")
URDF = os.path.join(ENV, "collision/surfaces/replicad_apartment_floor.urdf")
GSO = os.path.join(WS, "models/gso/Whey_Protein_Vanilla")
SUPPORT_H = 0.08232

def run(mu, v0, spin, mass=0.0018):
    scratch = tempfile.mkdtemp(prefix="sw_")
    scene = kb.Scene(frame_start=0, frame_end=80, frame_rate=16, step_rate=240,
                     gravity=(0,0,-9.81))
    sim = PyBullet(scene, scratch)
    surf = kb.FileBasedObject(name="surface", asset_id="floor",
        simulation_filename=URDF, render_filename=None, scale=(1,1,1),
        static=True, background=True, segmentation_id=1)
    scene += surf
    body = kb.FileBasedObject(name="actor", asset_id="whey",
        simulation_filename=os.path.join(GSO,"object.urdf"),
        render_filename=None, scale=(1,1,1), static=False,
        position=(0.0, -2.0, 0.0007 + SUPPORT_H), segmentation_id=2)
    scene += body
    bid = body.linked_objects[sim]
    pbc.changeDynamics(bid, -1, mass=mass, lateralFriction=mu,
                       rollingFriction=0.0, spinningFriction=0.0, restitution=0.1)
    pbc.resetBaseVelocity(bid, [v0, 0, 0], [0, 0, spin])
    sp, xs = [], []
    for f in range(81):
        for _ in range(15):
            pbc.stepSimulation()
        p, _q = pbc.getBasePositionAndOrientation(bid)
        lv, _av = pbc.getBaseVelocity(bid)
        sp.append(math.hypot(lv[0], lv[1])); xs.append(p[0])
    return sp, xs

print("SW v0=0.20 m/s, spin=0 (pure slide), 81 frames")
print("SW   mu    v0      v40     v80     travel   rel_change  monotonic")
for mu in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08):
    sp, xs = run(mu, 0.20, 0.0)
    rc = max(abs(v - sp[0]) for v in sp) / max(sp[0], 1e-9)
    mono = all(sp[i+1] <= sp[i] + 1e-6 for i in range(len(sp)-1))
    print("SW  %.3f  %.4f  %.4f  %.4f  %6.3f   %.4f     %s" % (
        mu, sp[0], sp[40], sp[80], abs(xs[80]-xs[0]), rc, mono))

print()
print("SW effect of the scenario's imposed spin at mu=0.02, v0=0.20:")
for spin in (0.0, 1.0, 2.43):
    sp, xs = run(0.02, 0.20, spin)
    rc = max(abs(v - sp[0]) for v in sp) / max(sp[0], 1e-9)
    print("SW  spin=%.2f  v0=%.4f v40=%.4f v80=%.4f travel=%.3f rel_change=%.4f" % (
        spin, sp[0], sp[40], sp[80], abs(xs[80]-xs[0]), rc))
PY
grep -E '^SW' "$WS/tmp/sweep.log" | head -25
