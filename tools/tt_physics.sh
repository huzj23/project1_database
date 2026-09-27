#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Turntable physics: does friction actually carry the actor?
#
# Kubric's PyBullet wrapper exposes run()/physics_client but NO step(), so the
# loop drives the client directly.  Bodies loaded as expected:
#     disc.linked_objects[sim] -> 1     actor -> 2
# and changeDynamics works, so the rig is sound; this measures the BEHAVIOUR.
#
# The disc is driven as a KINEMATIC body at constant angular velocity and
# PyBullet resolves contact + friction every step.  "The actor goes in a circle"
# is therefore a consequence of contact, not a scripted path -- which is the
# whole point of using a turntable instead of animating a circle.
#
# Swept over spin rates, because "how fast before the actor is thrown off" is a
# property of the friction coefficient and not something to guess.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" <<'PY' 2>&1 | grep -E '^TT'
import sys, os, json, tempfile, math
WS = sys.argv[1]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import pybullet as pbc

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
DISC_R, DISC_T, DISC_Z = 0.55, 0.03, 0.05
FPS, N = 24, 48


def run(omega, friction=1.2, r0=0.30):
    scratch = tempfile.mkdtemp(prefix="tt_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=N - 1,
                     frame_rate=FPS, step_rate=240, gravity=(0, 0, -9.81))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)

    scene += kb.Cube(name="ground", scale=(4, 4, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)

    disc = kb.FileBasedObject(
        name="turntable", asset_id="turntable",
        simulation_filename=os.path.join(TT, "collision/model.urdf"),
        render_filename=os.path.join(TT, "visual/model.obj"),
        scale=(1.0, 1.0, 1.0), static=True,
        position=(0, 0, DISC_Z - DISC_T / 2.0), segmentation_id=3)
    scene += disc

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]
    rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(r0, 0.0, DISC_Z + rest), segmentation_id=2)
    scene += obj

    did = disc.linked_objects[sim]
    oid = obj.linked_objects[sim]
    pbc.changeDynamics(did, -1, mass=0, lateralFriction=friction,
                       restitution=0.0, spinningFriction=0.02, rollingFriction=0.005)

    # Drive the disc by SETTING ITS VELOCITY ONCE and letting the solver integrate
    # its rotation.  Teleporting the pose every step (the previous approach) kept
    # resetting the contact manifold, so friction never had a chance to build up
    # and the actor never moved at all (slip 0.00).
    pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, omega])
    xs, ys, zs = [], [], []
    for f in range(N):
        pbc.stepSimulation()
        p, _ = pbc.getBasePositionAndOrientation(oid)
        xs.append(p[0]); ys.append(p[1]); zs.append(p[2])

    xs, ys, zs = np.array(xs), np.array(ys), np.array(zs)
    rs = np.hypot(xs, ys)
    ang = np.unwrap(np.arctan2(ys, xs))
    return dict(swept=math.degrees(ang[-1] - ang[0]),
                expected=math.degrees(omega * (N - 1) / FPS),
                r0=float(rs[0]), r1=float(rs[-1]), rmax=float(rs.max()),
                z_end=float(zs[-1]))


print("TT turntable physics: actor starts at r=0.30 m on a 0.55 m disc (friction 1.2)")
print(f"TT {'omega':>7}{'swept':>10}{'disc':>10}{'slip':>7}{'r_end':>8}{'rmax':>8}  on_disc")
for w in (0.4, 0.8, 1.2, 2.0, 3.0, 4.5):
    r = run(w)
    slip = abs(r["swept"]) / abs(r["expected"]) if r["expected"] else 0.0
    print(f"TT {w:7.2f}{r['swept']:9.1f}d{r['expected']:9.1f}d{slip:7.2f}"
          f"{r['r1']:8.3f}{r['rmax']:8.3f}  {bool(r['rmax'] < DISC_R)}")
print("TT slip~1.0 => carried by friction;  slip~0.0 => disc spins underneath")
PY
