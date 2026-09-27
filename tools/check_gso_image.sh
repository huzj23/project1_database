#!/usr/bin/env bash
# Why does the GSO actor render black?  Inspect the imported material's image
# datablock: a node can exist while its image failed to load (relative path).
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - "$WS" <<'PY' 2>&1 | grep -E '^IMG|^  '
import sys, os, tempfile
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
import bpy

GSO = "Sootheze_Cold_Therapy_Elephant"
GD = os.path.join(WS, "models/gso", GSO)
print(f"IMG cwd while importing = {os.getcwd()}")

scratch = tempfile.mkdtemp(prefix="img_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
sim = PyBullet(scene, scratch)
obj = kb.FileBasedObject(
    name=GSO, simulation_filename=os.path.join(GD, "object.urdf"),
    render_filename=os.path.join(GD, "visual_geometry.obj"),
    scale=1.0, position=(0, 0, 0), segmentation_id=2)
scene += obj
print("IMG actor added")

bo = obj.linked_objects.get(renderer)
print(f"IMG actor datablock = {bo.name if bo else None}")
data = bo.data
print(f"IMG uv layers = {[l.name for l in data.uv_layers]}")
for i, m in enumerate(data.materials):
    print(f"IMG material[{i}] = {m.name if m else None}  use_nodes={m.use_nodes if m else None}")
    if not m or not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE":
            im = n.image
            print(f"  IMG tex node '{n.name}' image={im.name if im else None}")
            if im:
                print(f"    filepath      = {im.filepath}")
                print(f"    filepath_raw  = {im.filepath_raw}")
                print(f"    size          = {tuple(im.size)}")
                print(f"    has_data      = {im.has_data}")
                print(f"    source        = {im.source}")
            linked = bool(n.outputs['Color'].links)
            print(f"    color output linked = {linked}")
print(f"IMG bpy.data.images = {[(i.name, tuple(i.size), i.has_data) for i in bpy.data.images]}")
PY
