#!/usr/bin/env bash
# ===========================================================================
# EMPIRICAL TEST of the re-extracted flat floor: drop the actor and read where it
# rests.  This is the measurement that matters -- rayTest returning 0 hits is a
# query artefact (thin static mesh), not proof the collision is absent.
#
# Expected if correct: rest centre z = surface.position[2] + support_height
#                                = 0.0007 + 0.08232 = 0.08302
# Before the fix it was 0.15386 (7.1 cm too high, supported_fraction 0.012).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' > "$WS/tmp/rest.log" 2>&1
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
SUPPORT_H, POS_Z = 0.08232, 0.0007
EXPECT = POS_Z + SUPPORT_H

scratch = tempfile.mkdtemp(prefix="rest_")
scene = kb.Scene(frame_start=0, frame_end=80, frame_rate=16, step_rate=240, gravity=(0,0,-9.81))
sim = PyBullet(scene, scratch)
surf = kb.FileBasedObject(name="surface", asset_id="floor",
    simulation_filename=URDF, render_filename=None, scale=(1,1,1),
    static=True, background=True, segmentation_id=1)
scene += surf
body = kb.FileBasedObject(name="actor", asset_id="whey",
    simulation_filename=os.path.join(GSO,"object.urdf"),
    render_filename=None, scale=(1,1,1), static=False,
    position=(-0.9, -0.96, POS_Z + SUPPORT_H + 0.15), segmentation_id=2)
scene += body
bid = body.linked_objects[sim]
pbc.changeDynamics(bid, -1, mass=0.0018, lateralFriction=0.06, restitution=0.1)
pbc.resetBaseVelocity(bid, [0.35, 0.0, 0.0], [0,0,0])

print("RS expected rest centre z = %.5f" % EXPECT)
sup = 0
for f in range(81):
    for _ in range(15):
        pbc.stepSimulation()
    p, _q = pbc.getBasePositionAndOrientation(bid)
    lv, _av = pbc.getBaseVelocity(bid)
    ok = abs(p[2] - EXPECT) <= 0.03
    sup += ok
    if f % 10 == 0 or f == 80:
        print("RS f%02d z=%.5f x=%+.4f |v|=%.4f supported=%s" % (
            f, p[2], p[0], math.hypot(lv[0],lv[1]), ok))
print("RS supported_fraction = %.4f" % (sup/81.0))
print("RS final travel = %.4f m" % abs(p[0] - (-0.9)))
PY
grep -E '^RS' "$WS/tmp/rest.log" | head -20
