#!/usr/bin/env bash
# ===========================================================================
# T2 PROBE 2: pin down the usable damping range with a STABLE body.
#
# Probe 1 showed k=0.5 decelerates (so Bullet's damping IS live) but the thin
# disc tipped (speed fell then rose), and k>=1.2 reported v=0 from the first
# sample.  Before writing the scenario we must know which k values give a clean
# exponential decay, so the motion can be validated on physics rather than on a
# tuned constant.
#
# Uses a box (stable, no tipping) and prints position too, so a body that never
# moved can be told apart from one that stopped.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^DQ'
import sys, os, tempfile, math
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
import pybullet as pbc

def say(*a): print("DQ", *a, flush=True)

def trial(ld, v0=1.0, nf=81):
    scratch = tempfile.mkdtemp(prefix="dq_")
    scene = kb.Scene(frame_start=0, frame_end=nf, frame_rate=16, step_rate=240,
                     gravity=(0, 0, -9.81))
    sim = PyBullet(scene, scratch)
    floor = kb.Cube(name="floor", scale=(5, 5, 0.05), position=(0, 0, -0.05),
                    static=True, segmentation_id=1)
    floor.material = kb.PrincipledBSDFMaterial(color=(0.5,0.5,0.5,1))
    scene += floor
    box = kb.Cube(name="slider", scale=(0.05, 0.05, 0.05), position=(0, 0, 0.05),
                  static=False, segmentation_id=2)
    box.material = kb.PrincipledBSDFMaterial(color=(0.8,0.2,0.2,1))
    scene += box
    bid = box.linked_objects[sim]
    pbc.changeDynamics(bid, -1, mass=0.05, lateralFriction=0.0,
                       rollingFriction=0.0, spinningFriction=0.0,
                       linearDamping=ld, angularDamping=ld)
    pbc.resetBaseVelocity(bid, [v0, 0, 0], [0, 0, 0])
    vs, xs = [], []
    for f in range(nf):
        for _ in range(15):
            pbc.stepSimulation()
        p, _q = pbc.getBasePositionAndOrientation(bid)
        lv, _av = pbc.getBaseVelocity(bid)
        vs.append(math.hypot(lv[0], lv[1])); xs.append(p[0])
    return vs, xs

say("box 0.1 m, v0=1.0 m/s, friction 0, 81 frames @16fps (5.06 s)")
say("  k      v[0]    v[20]   v[40]   v[80]   x[80]    verdict")
for ld in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.6, 2.0):
    vs, xs = trial(ld)
    moved = abs(xs[80]) > 1e-4
    mono = all(vs[i+1] <= vs[i] + 1e-6 for i in range(len(vs)-1))
    verdict = "no effect" if abs(vs[80]-vs[0]) < 1e-3 else ("clean decay" if mono else "NON-monotonic")
    say(f"  {ld:4.1f}  {vs[0]:.4f}  {vs[20]:.4f}  {vs[40]:.4f}  {vs[80]:.4f}  {xs[80]:7.4f}  {verdict} moved={moved}")

say("")
say("exponential fit for k=0.4 and k=0.8:")
for ld in (0.4, 0.8):
    vs, xs = trial(ld)
    say(f"  k={ld}: measured vs analytic exp(-k*t)")
    for f in (0, 20, 40, 80):
        t = f/16.0
        say(f"    f{f:02d} t={t:.2f}s measured={vs[f]:.4f} analytic={math.exp(-ld*t):.4f}")
PY
