#!/usr/bin/env bash
# ===========================================================================
# ROOT CAUSE CHECK: is the extracted floor mesh really flat?
#
# The actor rested at z = 0.15386 (bottom ~0.0709) instead of 0.08302.  So the
# extracted mesh is NOT flat: my band selection (upward faces with face-centre
# z in [0, 0.05)) also captured raised geometry.
#
# supported_fraction compares every frame against ONE height
# (surface.position[2] + support_height), which can only be right for a surface
# that really is flat.  So the fix is to extract ONLY the flat walking surface.
#
# Measure by ray-casting the extracted mesh over the clear rectangle.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/vendor/phyco-sim" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' > "$WS/tmp/raycast2.log" 2>&1
import sys, os, tempfile
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

scratch = tempfile.mkdtemp(prefix="rc2_")
scene = kb.Scene(frame_start=0, frame_end=0, frame_rate=16, step_rate=240, gravity=(0,0,-9.81))
sim = PyBullet(scene, scratch)
surf = kb.FileBasedObject(name="surface", asset_id="floor",
    simulation_filename=URDF, render_filename=None, scale=(1,1,1),
    static=True, background=True, segmentation_id=1)
scene += surf
bid = surf.linked_objects[sim]

print("RAY ray-cast the extracted floor mesh, clear rect x[-1.9,3.2] y[-4.0,-0.3]")
zs = []
for x in np.arange(-1.8, 3.1, 0.3):
    for y in np.arange(-3.9, -0.4, 0.3):
        hit = pbc.rayTest([float(x), float(y), 2.0], [float(x), float(y), -0.5])
        if hit and hit[0] == bid:
            zs.append((float(x), float(y), float(hit[3][2])))
arr = np.array([z for _, _, z in zs])
print("RAY samples=%d" % len(zs))
print("RAY hit z: min=%.5f max=%.5f mean=%.5f median=%.5f" % (
    arr.min(), arr.max(), arr.mean(), np.median(arr)))
for thr in (0.002, 0.005, 0.01, 0.05):
    print("RAY fraction z<=%.3f : %.3f" % (thr, (arr <= thr).mean()))
print("RAY non-flat samples (z>0.005):")
n = 0
for x, y, z in zs:
    if z > 0.005:
        print("RAY   x=%+.2f y=%+.2f z=%.5f" % (x, y, z))
        n += 1
        if n > 25:
            print("RAY   ...")
            break
PY

grep -E '^RAY' "$WS/tmp/raycast2.log" | head -45
