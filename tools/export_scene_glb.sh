#!/usr/bin/env bash
# Export the ReplicaCAD apartment as ONE combined visual GLB:
#   frl_apartment_stage  +  all props from apt_0.scene_instance.json
#
# The mentor's environment manifest expects a single `visual/scene.glb` that the
# renderer imports as the backdrop.  ReplicaCAD ships the shell and the furniture
# separately, so they are merged here once and cached.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^EXP|^  '
import sys, os, json, tempfile
WS, REPO = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.renderer import Blender
import bpy

R = os.path.join(WS, "models/backgrounds/replicad")
OUT = os.path.join(REPO, "assets/environments/replicad_apartment/visual")
os.makedirs(OUT, exist_ok=True)
target = os.path.join(OUT, "scene.glb")

scratch = tempfile.mkdtemp(prefix="exp_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)

# clear the default cube/light/camera so only the apartment is exported
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
n_stage = len([o for o in bpy.data.objects if o.type == "MESH"])
print(f"EXP stage meshes: {n_stage}")

cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
placed = 0
for inst in cfg.get("object_instances", []):
    tpl = inst["template_name"].split("/")[-1]
    glb = os.path.join(R, "objects", f"{tpl}.glb")
    if not os.path.isfile(glb):
        continue
    b2 = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception:
        continue
    tr = inst.get("translation", [0, 0, 0])
    for o in [o for o in bpy.data.objects if o.name not in b2]:
        if o.parent is None:
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))
    placed += 1

n_all = len([o for o in bpy.data.objects if o.type == "MESH"])
print(f"EXP props placed: {placed}   total meshes: {n_all}")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(
    filepath=target,
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_yup=True,
)
size = os.path.getsize(target) / 1048576
print(f"EXP wrote {target}  ({size:.1f} MB)")
PY
