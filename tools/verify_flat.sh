#!/usr/bin/env bash
# ===========================================================================
# VERIFY the re-extracted flat floor: every ray inside the clear rectangle must
# hit the floor plane, not a raised surface.
#
# This is the check that failed before (a hit at z=0.084 caused a 7.1 cm rest
# error and supported_fraction 0.012).  It must now pass everywhere.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== OBJ bounds (correct per-axis) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import numpy as np
p="/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment/collision/surfaces/replicad_apartment_floor.obj"
V=[]
for ln in open(p):
    if ln.startswith("v "): V.append([float(x) for x in ln.split()[1:4]])
V=np.array(V)
print(f"  verts={len(V)}")
for i,ax in enumerate("xyz"):
    print(f"  {ax}: [{V[:,i].min():.4f}, {V[:,i].max():.4f}]  span={V[:,i].max()-V[:,i].min():.4f}")
print(f"  -> z spread = {V[:,2].max()-V[:,2].min():.5f} m (flat if small)")
PY

echo
echo "=== raycast the new mesh across the clear rectangle ==="
cd "$WS/code/vendor/phyco-sim" || exit 1
"$WS/tools/conda_env/bin/python" - <<'PY' > "$WS/tmp/verify_flat.log" 2>&1
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

scratch = tempfile.mkdtemp(prefix="vf_")
scene = kb.Scene(frame_start=0, frame_end=0, frame_rate=16, step_rate=240, gravity=(0,0,-9.81))
sim = PyBullet(scene, scratch)
surf = kb.FileBasedObject(name="surface", asset_id="floor",
    simulation_filename=URDF, render_filename=None, scale=(1,1,1),
    static=True, background=True, segmentation_id=1)
scene += surf
bid = surf.linked_objects[sim]
print("VF AABB:", pbc.getAABB(bid, -1))

zs = []
miss = 0
for x in np.arange(-1.8, 3.1, 0.25):
    for y in np.arange(-3.9, -0.4, 0.25):
        hit = pbc.rayTest([float(x), float(y), 2.0], [float(x), float(y), -0.5])
        if hit and hit[0] == bid:
            zs.append(float(hit[3][2]))
        else:
            miss += 1
arr = np.array(zs)
print("VF samples=%d misses=%d" % (len(zs), miss))
if len(arr):
    print("VF hit z: min=%.5f max=%.5f mean=%.5f std=%.6f" % (
        arr.min(), arr.max(), arr.mean(), arr.std()))
    print("VF fraction |z-0.0007|<=0.01 : %.4f" % (np.abs(arr-0.0007) <= 0.01).mean())
    bad = arr[np.abs(arr-0.0007) > 0.01]
    print("VF non-floor hits: %d %s" % (len(bad), np.round(bad[:10],4).tolist()))
PY
grep -E '^VF' "$WS/tmp/verify_flat.log" | head -15
