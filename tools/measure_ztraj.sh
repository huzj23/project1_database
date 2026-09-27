#!/usr/bin/env bash
# ===========================================================================
# Directly measure the ACTUAL z trajectory of a sliding actor on the extracted
# floor mesh, and compare against the expected rest height.
#
# supported_fraction compares |z - (surface.position[2] + support_height)| <= 3 cm.
# The floor's walking surface is at z ~ 0.0007 (80.96 of 81.61 m^2), which matches
# position[2] = 0.0007 to 0.3 mm.  So the mesh top is NOT the problem -- the body
# must not be resting at the expected height for another reason.
#
# This runs the real backend and prints z, plus the contact count, frame by frame.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' > "$WS/tmp/ztraj.log" 2>&1
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
POS_Z = 0.0007

scratch = tempfile.mkdtemp(prefix="zt_")
scene = kb.Scene(frame_start=0, frame_end=80, frame_rate=16, step_rate=240, gravity=(0,0,-9.81))
sim = PyBullet(scene, scratch)
surf = kb.FileBasedObject(name="surface", asset_id="floor",
    simulation_filename=URDF, render_filename=None, scale=(1,1,1),
    static=True, background=True, segmentation_id=1)
scene += surf
body = kb.FileBasedObject(name="actor", asset_id="whey",
    simulation_filename=os.path.join(GSO,"object.urdf"),
    render_filename=None, scale=(1,1,1), static=False,
    position=(-0.9, -0.96, POS_Z + SUPPORT_H), segmentation_id=2)
scene += body
bid = body.linked_objects[sim]
pbc.changeDynamics(bid, -1, mass=0.0018, lateralFriction=0.06, restitution=0.1)
pbc.resetBaseVelocity(bid, [0.35, 0.0, 0.0], [0,0,0])

print("EXPECTED rest centre z = %.5f" % (POS_Z + SUPPORT_H))
print("frame   z        x        |v|      contacts  supported")
sup = 0
for f in range(81):
    for _ in range(15):
        pbc.stepSimulation()
    p, _q = pbc.getBasePositionAndOrientation(bid)
    lv, _av = pbc.getBaseVelocity(bid)
    cps = pbc.getContactPoints(bodyA=bid)
    n = len(cps)
    ok = abs(p[2] - (POS_Z + SUPPORT_H)) <= 0.03
    sup += ok
    if f % 8 == 0 or f == 80:
        print("%5d  %.5f  %+.4f  %.4f   %4d      %s" % (f, p[2], p[0], math.hypot(lv[0],lv[1]), n, ok))
print()
print("supported_fraction = %.4f" % (sup/81.0))
PY

grep -vE '^$' "$WS/tmp/ztraj.log" | head -30
