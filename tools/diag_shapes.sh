#!/usr/bin/env bash
# ===========================================================================
# DECISIVE: what geometry is actually in the support body, and where does a body
# rest on it?
#
# rayTest returned 0 hits, so the URDF mesh may not have loaded as a collidable
# body at all (or its frame is offset).  Two checks:
#   1. how many collision shapes does the body have, and what are their AABBs?
#   2. what is the body's base position/orientation as loaded?
#
# This tells us whether `collision: type: mesh` is even functioning, which decides
# the whole approach for the "delete the patch floor" requirement.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' > "$WS/tmp/shapes.log" 2>&1
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np, kubric as kb, phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
import pybullet as pbc

WS = "/data/raw/hujian/project1_database" if False else "/data/raw/huzijian/project1_database"
ENV = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment")
URDF = os.path.join(ENV, "collision/surfaces/replicad_apartment_floor.urdf")
print("SH urdf exists:", os.path.isfile(URDF))
print("SH urdf text:", open(URDF).read().replace("\n", " ")[:200])

scratch = tempfile.mkdtemp(prefix="sh_")
scene = kb.Scene(frame_start=0, frame_end=0, frame_rate=16, step_rate=240, gravity=(0,0,-9.81))
sim = PyBullet(scene, scratch)
surf = kb.FileBasedObject(name="surface", asset_id="floor",
    simulation_filename=URDF, render_filename=None, scale=(1,1,1),
    static=True, background=True, segmentation_id=1)
scene += surf
bid = surf.linked_objects[sim]
print("SH body id:", bid)
n = pbc.getNumJoints(bid)
print("SH num joints:", n)
try:
    aabb = pbc.getAABB(bid, -1)
    print("SH AABB min:", aabb[0], "max:", aabb[1])
except Exception as e:
    print("SH AABB error:", e)
print("SH base pos/orient:", pbc.getBasePositionAndOrientation(bid))
# how many collision shapes were actually created?
try:
    shapes = pbc.getCollisionShapeData(bid, -1)
    print("SH collision shapes:", len(shapes))
    for s in shapes[:6]:
        print("SH   ", s)
except Exception as e:
    print("SH shape error:", e)
# try a ray straight down from directly above the origin
for z0 in (5.0, 1.0):
    hit = pbc.rayTest([0.65, -2.15, z0], [0.65, -2.15, -1.0])
    print("SH rayTest from z=%.1f ->" % z0, hit)
PY

grep -E '^SH' "$WS/tmp/shapes.log" | head -30
