#!/usr/bin/env bash
# ===========================================================================
# Measure the TRUE top surface of the floor slab, so surface.position[2] can be
# set to the height a body actually rests at.
#
# The extracted mesh is a slab with thickness: face-centre z runs 0.0007..0.0497
# with median 0.035.  supported_fraction compares against a SINGLE expected
# height (surface.position[2] + support_height) with a 3 cm tolerance, so the
# expected height must be the real walking surface, not the slab's mid-plane.
#
# Method: for each floor face, print its z; and separately, drop a test body and
# read where it comes to rest.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== z distribution of the 202 extracted floor faces ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import numpy as np
p = "assets/environments/replicad_apartment/collision/surfaces/replicad_apartment_floor.obj"
V, F = [], []
for ln in open(p):
    if ln.startswith("v "):
        V.append([float(x) for x in ln.split()[1:4]])
    elif ln.startswith("f "):
        F.append([int(x.split("/")[0]) - 1 for x in ln.split()[1:4]])
V = np.array(V); F = np.array(F)
tris = V[F]
zc = tris[:, :, 2].mean(axis=1)
area = 0.5 * np.linalg.norm(np.cross(tris[:,1]-tris[:,0], tris[:,2]-tris[:,0]), axis=1)
order = np.argsort(zc)
print(f"  {'z':>9} {'area':>8}   (sorted)")
run = 0.0
for i in order:
    run += area[i]
    if i % 1 == 0 and (zc[i] < 0.01 or abs(zc[i]-0.035) < 0.002 or zc[i] > 0.045):
        pass
# histogram by area
h, e = np.histogram(zc, bins=np.arange(-0.005, 0.055, 0.005), weights=area)
for i, c in enumerate(h):
    if c > 0:
        print(f"  [{e[i]:+.3f},{e[i+1]:+.3f})  {c:7.3f} m^2")
print()
print(f"  total area       = {area.sum():.2f} m^2")
print(f"  area with z<0.01 = {area[zc<0.01].sum():.2f} m^2")
print(f"  area with z<0.02 = {area[zc<0.02].sum():.2f} m^2")
print(f"  area-weighted mean z = {(zc*area).sum()/area.sum():.5f}")
print(f"  MIN z over faces = {zc.min():.5f}   (this is the lowest walking surface)")
PY

echo
echo "=== EMPIRICAL: where does a body actually come to rest? ==="
cd "$WS/code/vendor/phyco-sim" || exit 1
"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^RS'
import sys, os, tempfile, math
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np, kubric as kb, phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
import pybullet as pbc

def say(*a): print("RS", *a, flush=True)
WS = "/data/raw/huzijian/project1_database"
URDF = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment/collision/surfaces/replicad_apartment_floor.urdf")
GSO = os.path.join(WS, "models/gso/Whey_Protein_Vanilla")

scratch = tempfile.mkdtemp(prefix="rs_")
scene = kb.Scene(frame_start=0, frame_end=10, frame_rate=16, step_rate=240, gravity=(0,0,-9.81))
sim = PyBullet(scene, scratch)
surf = kb.FileBasedObject(name="surface", asset_id="floor",
    simulation_filename=URDF, render_filename=None, scale=(1,1,1),
    static=True, background=True, segmentation_id=1)
scene += surf
# drop the actor at several XY inside the clear rectangle
for (x, y) in [(-0.9,-0.96), (0.0,-2.0), (1.5,-3.0), (2.5,-1.0)]:
    body = kb.FileBasedObject(name=f"b_{x}_{y}", asset_id="whey",
        simulation_filename=os.path.join(GSO,"object.urdf"),
        render_filename=None, scale=(1,1,1), static=False,
        position=(x, y, 0.5), segmentation_id=2)
    scene += body
    bid = body.linked_objects[sim]
    pbc.changeDynamics(bid, -1, mass=0.0018, lateralFriction=0.06, restitution=0.1)
for _ in range(600):
    pbc.stepSimulation()
for (x, y) in [(-0.9,-0.96), (0.0,-2.0), (1.5,-3.0), (2.5,-1.0)]:
    b = [o for o in scene.instances if o.name == f"b_{x}_{y}"][0]
    p, _q = pbc.getBasePositionAndOrientation(b.linked_objects[sim])
    say(f"  rest at ({x:+.1f},{y:+.1f}) -> centre z = {p[2]:.5f}")
say("  support_height of this actor = 0.08232")
say("  => implied floor TOP z = centre_z - support_height")
PY
