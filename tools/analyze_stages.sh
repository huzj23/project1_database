#!/usr/bin/env bash
# Characterise a ReplicaCAD stage so we can place the subject ON its floor and
# put the camera inside the room:
#   * true world-space bounds (evaluated vertices, not bound_box)
#   * the dominant horizontal surface (the floor) and its height
#   * a sensible camera stand-off
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - <<'PY' 2>&1 | grep -vE '^Fra:|^Saved:|^ ?Time:|^ *$'
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

WS = "/data/raw/huzijian/project1_database"
STAGES = sorted(f[:-4] for f in os.listdir(os.path.join(WS, "models/backgrounds/replicad/stages"))
                if f.endswith(".glb"))

for stage in STAGES[:3]:
    scratch = tempfile.mkdtemp(prefix="stage_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    glb = os.path.join(WS, "models/backgrounds/replicad/stages", f"{stage}.glb")
    bg = kb.FileBasedObject(name="stage", simulation_filename=None,
                            render_filename=glb, static=True, background=True,
                            segmentation_id=1)
    scene += bg

    dg = bpy.context.evaluated_depsgraph_get()
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    zs = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        if not len(me.vertices):
            continue
        co = np.array([v.co[:] for v in me.vertices])
        mw = np.array(o.matrix_world)
        world = co @ mw[:3, :3].T + mw[:3, 3]
        lo = np.minimum(lo, world.min(axis=0))
        hi = np.maximum(hi, world.max(axis=0))
        zs.append(world[:, 2])
        o.evaluated_get(dg).to_mesh_clear()

    print(f"STAGE {stage}")
    print(f"   world bounds  min={np.round(lo,2).tolist()}  max={np.round(hi,2).tolist()}")
    print(f"   extents (m)   {np.round(hi-lo,2).tolist()}")
    if zs:
        allz = np.concatenate(zs)
        # the floor is the strongest mode of the z distribution
        hist, edges = np.histogram(allz, bins=60)
        k = int(np.argmax(hist))
        print(f"   floor z ~ {edges[k]:.2f}  (histogram peak, {hist[k]} verts)")
        print(f"   z percentiles 1/50/99 = "
              f"{np.percentile(allz,1):.2f} / {np.percentile(allz,50):.2f} / {np.percentile(allz,99):.2f}")
    # free horizontal extent at floor level, where the subject can move
    print(f"   usable footprint {np.round(hi[:2]-lo[:2],2).tolist()} m")
    print()

    # drop it again to keep memory flat
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
PY
