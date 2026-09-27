#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# FINAL turntable confirmation, stepped at the correct physics rate.
#
# The previous run looked 10x slow because Kubric's client steps at 1/240 s while
# I stepped once per VIDEO frame: 47 steps = 0.196 s of simulated time, not 1.96 s.
# The angles matched that exactly (13.5 deg vs 1.2 rad/s x 0.196 s), which is what
# confirmed the physics itself was right.
#
# Rig, as established:
#   * disc loaded with static=FALSE.  static=True makes Kubric pass
#     useFixedBase=True, which BOLTS the disc in place -- it can never rotate.
#   * disc kept DYNAMIC and its angular velocity re-applied every step: that is
#     the motor.  mass=0 would make it static again and it would not turn.
#   * position pinned, orientation carried through, so the disc visibly spins.
#   * 240 steps per video frame.
#
# Output: does friction carry the actor, at what slip, and over what speed range.
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
PHYS_FPS, VIDEO_FPS, SECONDS = 240, 16, 3.0
NSTEPS = int(PHYS_FPS * SECONDS)
SUB = PHYS_FPS // VIDEO_FPS


def run(omega, friction=1.2, r0=0.30, mass_scale=1.0):
    scratch = tempfile.mkdtemp(prefix="ttf_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=8,
                     frame_rate=VIDEO_FPS, step_rate=PHYS_FPS, gravity=(0, 0, -9.81))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    scene += kb.Cube(name="ground", scale=(4, 4, 0.1), position=(0, 0, -0.1), static=True)

    disc = kb.FileBasedObject(
        name="turntable", asset_id="turntable",
        simulation_filename=os.path.join(TT, "collision/model.urdf"),
        render_filename=os.path.join(TT, "visual/model.obj"),
        scale=(1.0, 1.0, 1.0), static=False,
        position=(0, 0, DISC_Z - DISC_T / 2.0), segmentation_id=3)
    scene += disc

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"] * mass_scale,
        scale=1.0, position=(r0, 0.0, DISC_Z + rest + 0.005), segmentation_id=2)
    scene += obj

    did = disc.linked_objects[sim]
    oid = obj.linked_objects[sim]
    pbc.changeDynamics(did, -1, lateralFriction=friction)
    pbc.changeDynamics(oid, -1, lateralFriction=friction)

    xs, ys, zs, dang = [], [], [], []
    for s in range(NSTEPS):
        cp, cq = pbc.getBasePositionAndOrientation(did)
        pbc.resetBasePositionAndOrientation(did, [0, 0, DISC_Z - DISC_T / 2.0], cq)
        pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, omega])
        pbc.stepSimulation()
        if s % SUB == 0:
            p, _ = pbc.getBasePositionAndOrientation(oid)
            _d, dq = pbc.getBasePositionAndOrientation(did)
            xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
            dang.append(math.degrees(pbc.getEulerFromQuaternion(dq)[2]))

    xs, ys, zs = np.array(xs), np.array(ys), np.array(zs)
    rs = np.hypot(xs, ys)
    a = np.unwrap(np.arctan2(ys, xs))
    return dict(swept=math.degrees(a[-1] - a[0]),
                disc=abs(dang[-1] - dang[0]),
                expected=math.degrees(omega * SECONDS),
                r0=float(rs[0]), r1=float(rs[-1]), rmax=float(rs.max()),
                z_end=float(zs[-1]))


print(f"TT turntable, stepped at {PHYS_FPS} Hz for {SECONDS}s ({NSTEPS} steps)")
print(f"TT {'omega':>7}{'actor':>10}{'disc':>9}{'expected':>10}{'slip':>7}{'r_end':>8}{'rmax':>8}  on_disc")
for w in (0.5, 1.0, 1.5, 2.5, 4.0):
    r = run(w)
    slip = abs(r["swept"]) / abs(r["disc"]) if r["disc"] else 0.0
    print(f"TT {w:7.2f}{r['swept']:9.1f}d{r['disc']:8.1f}d{r['expected']:9.1f}d"
          f"{slip:7.2f}{r['r1']:8.3f}{r['rmax']:8.3f}  {bool(r['rmax'] < DISC_R)}")
print("TT slip = actor angle / disc angle: ~1.0 means it rides along with the disc")
PY
