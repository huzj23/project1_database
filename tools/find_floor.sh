#!/usr/bin/env bash
# Robust floor detection for ReplicaCAD stages.
#
# Vertex bounds are useless here: the GLBs carry outlier geometry that inflates
# the bounding box to hundreds of metres.  A downward ray-grid finds the actual
# walkable floor and an open area to place the subject in.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - <<'PY' 2>&1 | grep -E '^STAGE|^   '
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy
from mathutils import Vector

WS = "/data/raw/huzijian/project1_database"
SDIR = os.path.join(WS, "models/backgrounds/replicad/stages")
STAGES = sorted(f[:-4] for f in os.listdir(SDIR) if f.endswith(".glb"))

for stage in STAGES:
    scratch = tempfile.mkdtemp(prefix="floor_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    glb = os.path.join(SDIR, f"{stage}.glb")
    scene += kb.FileBasedObject(name="stage", simulation_filename=None,
                                render_filename=glb, static=True,
                                background=True, segmentation_id=1)

    dg = bpy.context.evaluated_depsgraph_get()
    print(f"STAGE {stage}")

    # Cast down over a coarse grid and collect hits
    hits = []
    R, STEP = 8.0, 1.0
    for x in np.arange(-R, R + 1e-9, STEP):
        for y in np.arange(-R, R + 1e-9, STEP):
            origin = Vector((float(x), float(y), 30.0))
            ok, loc, nrm, _ = bpy.context.scene.ray_cast(dg, origin, Vector((0, 0, -1)))
            if ok and nrm.z > 0.9:          # near-horizontal surface = floor-ish
                hits.append((float(x), float(y), float(loc.z)))
    if not hits:
        print("   no floor hits found")
        bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
        continue

    a = np.array(hits)
    z = a[:, 2]
    # the floor is the most common height band
    hist, edges = np.histogram(z, bins=80)
    k = int(np.argmax(hist))
    floor_z = 0.5 * (edges[k] + edges[k + 1])
    band = np.abs(z - floor_z) < 0.08
    pts = a[band]
    print(f"   floor z  = {floor_z:.2f} m   ({band.sum()} hits within +/-8 cm)")
    if len(pts):
        print(f"   floor xy = x[{pts[:,0].min():.1f},{pts[:,0].max():.1f}] "
              f"y[{pts[:,1].min():.1f},{pts[:,1].max():.1f}]  "
              f"span {pts[:,0].ptp():.1f} x {pts[:,1].ptp():.1f} m")
        # largest empty-ish disc: use the centroid of the floor points
        cx, cy = float(np.median(pts[:, 0])), float(np.median(pts[:, 1]))
        d = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
        print(f"   suggested subject spot = ({cx:.1f}, {cy:.1f}, {floor_z:.2f})")
        print(f"   clear radius around it ~ {np.percentile(d, 40):.1f} m")
    print(f"   total floor-ish hits   = {len(hits)}")

    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
    print()
PY
