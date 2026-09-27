#!/usr/bin/env bash
# Locate the ReplicaCAD stage's floor height with a handful of single raycasts
# (a dense grid was far too slow on this geometry), and check whether the stage
# can receive shadows at all.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - "$WS" <<'PY' 2>&1 | grep -E '^RAY|^  '
import sys, os, tempfile
WS = sys.argv[1]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
import phyco_backdrops as pb
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy
from mathutils import Vector

for stage in ("frl_apartment_stage", "Stage_v3_sc0_staging"):
    scratch = tempfile.mkdtemp(prefix="ray_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    scene += kb.FileBasedObject(
        name="stage", simulation_filename=None,
        render_filename=os.path.join(WS, "models/backgrounds/replicad/stages",
                                     f"{stage}.glb"),
        static=True, background=True, segmentation_id=1)
    dg = bpy.context.evaluated_depsgraph_get()
    print(f"RAY stage={stage}")
    for (x, y) in [(0, 0), (0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5), (1.0, 1.0)]:
        ok, loc, nrm, idx, obj, _ = bpy.context.scene.ray_cast(
            dg, Vector((x, y, 20.0)), Vector((0, 0, -1)), distance=60.0)
        if ok:
            print(f"  ({x:+.1f},{y:+.1f}) hit z={loc.z:8.3f}  n.z={nrm.z:+.2f}  obj={obj.name[:28]}")
        else:
            print(f"  ({x:+.1f},{y:+.1f}) no hit")
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
    print()
PY
