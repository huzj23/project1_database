#!/usr/bin/env bash
# ===========================================================================
# T2 PROBE: does PyBullet's linearDamping/angularDamping actually decelerate a
# body through the Kubric wrapper?
#
# V1.0 recorded that `changeDynamics` damping "returned success but silently did
# nothing" -- but that was under `useMaximalCoordinates`.  The current backend
# uses the default (maximal) coordinates and real integration, so the behaviour
# must be re-measured rather than inherited from an old note.
#
# This decides how motion #7 (damping) is implemented:
#   * if damping works -> set it via changeDynamics and let Bullet integrate
#   * if it does not    -> we must NOT fake it by resetting velocity each frame
#                          (that would violate iron rule 1), so the motion would
#                          be reported as blocked instead
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^DP'
import sys, os, tempfile, math
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join("/data/raw/huzijian/project1_database", "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
import pybullet as pbc

def say(*a): print("DP", *a, flush=True)

WS = "/data/raw/huzijian/project1_database"
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")

def trial(lin_damp, ang_damp, v0=1.0):
    scratch = tempfile.mkdtemp(prefix="dp_")
    scene = kb.Scene(frame_start=0, frame_end=60, frame_rate=16, step_rate=240,
                     gravity=(0, 0, -9.81))
    sim = PyBullet(scene, scratch)
    # a flat support so the body has something to slide on
    floor = kb.Cube(name="floor", scale=(5, 5, 0.05), position=(0, 0, -0.05),
                    static=True, segmentation_id=1)
    floor.material = kb.PrincipledBSDFMaterial(color=(0.5,0.5,0.5,1))
    scene += floor
    # use the turntable disc as a simple cylindrical slider
    body = kb.FileBasedObject(
        name="slider", asset_id="turntable",
        simulation_filename=os.path.join(TT, "collision/model.urdf"),
        render_filename=None, scale=(1.0,1.0,1.0), static=False,
        position=(0, 0, 0.011), segmentation_id=2)
    scene += body
    bid = body.linked_objects[sim]
    pbc.changeDynamics(bid, -1, mass=1.0, lateralFriction=0.0,
                       rollingFriction=0.0, spinningFriction=0.0,
                       linearDamping=lin_damp, angularDamping=ang_damp)
    pbc.resetBaseVelocity(bid, [v0, 0, 0], [0, 0, 0])
    speeds = []
    for f in range(60):
        for _ in range(15):
            pbc.stepSimulation()
        p, _q = pbc.getBasePositionAndOrientation(bid)
        lv, _av = pbc.getBaseVelocity(bid)
        speeds.append(math.hypot(lv[0], lv[1]))
    return speeds

say("v0 = 1.0 m/s, friction 0, 60 video frames (1/16 s each)")
for ld in (0.0, 0.5, 1.2, 3.0):
    s = trial(ld, ld)
    say(f"  linearDamping={ld:4.1f}: v[0]={s[0]:.4f} v[8]={s[8]:.4f} "
        f"v[30]={s[30]:.4f} v[59]={s[59]:.4f}  -> {'WORKS' if abs(s[59]-s[0])>1e-3 else 'NO EFFECT'}")
say("")
s = trial(1.2, 1.2)
say("  decay check for k=1.2 (analytic v0*exp(-k*t), t = frame/16):")
for f in (0, 8, 16, 30, 59):
    t = f/16.0
    say(f"    f{f:02d} t={t:.3f}s measured={s[f]:.4f} analytic={math.exp(-1.2*t):.4f} "
        f"ratio={s[f]/max(math.exp(-1.2*t),1e-9):.3f}")
PY
