#!/usr/bin/env bash
# Why doesn't the actor move?  Print the frames.
export LC_ALL=C
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

scratch = tempfile.mkdtemp(prefix="ttd_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=47,
                 frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
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
ACTOR_Z = DISC_Z + rest + 0.01          # 1 cm above the disc, so it settles onto it
obj = kb.FileBasedObject(
    name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
    render_filename=os.path.join(GSO, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
    scale=1.0, position=(0.30, 0.0, ACTOR_Z), segmentation_id=2)
scene += obj

did = disc.linked_objects[sim]
oid = obj.linked_objects[sim]
print(f"TT body ids disc={did} actor={oid}")
print(f"TT disc top z should be {DISC_Z:.3f}; actor lowest point starts at {ACTOR_Z - rest:.3f}")
print(f"TT actor mass = {meta['kwargs']['mass']:.6f} kg  (very light!)")

# NOTE: mass=0 makes a body STATIC in PyBullet -- it does not move at all, even
# with a velocity set (that is why the disc's orientation never changed).  A real
# turntable is motor-driven, so keep the disc DYNAMIC and re-apply its angular
# velocity each step: friction with the actor then bleeds off a little speed and
# the motor puts it back, exactly like the real thing.
pbc.changeDynamics(did, -1, lateralFriction=1.2, restitution=0.0)
d0 = pbc.getDynamicsInfo(did, -1)
a0 = pbc.getDynamicsInfo(oid, -1)
print(f"TT disc  dynamics: mass={d0[0]} latFric={d0[1]}")
print(f"TT actor dynamics: mass={a0[0]:.6f} latFric={a0[1]}")

omega = 1.2
pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, omega])
print(f"TT driving disc at omega={omega} rad/s (velocity set once)")
print(f"TT {'f':>3} {'actor x':>9} {'actor y':>9} {'actor z':>9} {'r':>7} {'disc ang':>9}")
for f in range(48):
    # Pin the disc's POSITION, but carry its CURRENT orientation through -- passing
    # a fresh identity quaternion each step (the previous version) also froze the
    # disc's visual rotation, so it would have looked stationary while the actor
    # still crept around it.
    _cp, _cq = pbc.getBasePositionAndOrientation(did)
    pbc.resetBasePositionAndOrientation(did, [0, 0, DISC_Z - DISC_T / 2.0], _cq)
    pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, omega])   # the "motor"
    pbc.stepSimulation()
    if f % 6 == 0 or f == 47:
        p, _ = pbc.getBasePositionAndOrientation(oid)
        dp, dq = pbc.getBasePositionAndOrientation(did)
        e = pbc.getEulerFromQuaternion(dq)
        print(f"TT {f:3d} {p[0]:9.4f} {p[1]:9.4f} {p[2]:9.4f} "
              f"{math.hypot(p[0],p[1]):7.4f} {math.degrees(e[2]):8.1f}d")
pv, _ = pbc.getBaseVelocity(oid)
print(f"TT actor velocity at end: lin={tuple(round(v,4) for v in pv)}")
dv, dw = pbc.getBaseVelocity(did)
print(f"TT disc  velocity at end: lin={tuple(round(v,4) for v in dv)} ang={tuple(round(v,4) for v in dw)}")
PY
