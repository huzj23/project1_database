#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Export the ReplicaCAD apartment as visual/scene.blend -- the format the mentor's
# pipeline actually prefers for environments:
#
#   "complex environments normally use visual/scene.blend so authored materials,
#    lights, and World can be preserved"   (his AGENTS.md)
#
# Why switch away from the GLB:
#   1. AXIS/PLACEMENT.  Our GLB was exported with export_yup=True and then
#      re-imported by the pipeline; the environment ended up reported as spanning
#      765 m, and the camera (correctly placed indoors) saw only flat background.
#      A .blend keeps the scene exactly as authored -- no round-trip conversion.
#   2. LIGHTING DOCTRINE (our 铁律四).  A .blend preserves the authored ceiling
#      lights; the GLB carried none, so the pipeline fell back to a single
#      synthetic AREA light ("environment_lighting_source: asset_fallback"),
#      which is precisely the "script quietly invents its own light" we banned.
#
# The authored lights come from configs/lighting/frl_apartment_stage.lighting_config.json
# (7 point lights) and are created here so the .blend is self-contained.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^BLEND|^  '
import sys, os, json, tempfile, math
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
target = os.path.join(OUT, "scene.blend")

scratch = tempfile.mkdtemp(prefix="bl_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)

# start from a clean file
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
stage = [o for o in bpy.data.objects if o.type == "MESH"]
print(f"BLEND stage meshes: {len(stage)}")

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
            # habitat is Y-up; our stage import is Z-up, so map (x,y,z)->(x,-z,y)
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))
    placed += 1
print(f"BLEND props placed: {placed}")

# --- authored lights, so the file is self-contained (铁律四) ----------------
lcfg = os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")
lj = json.load(open(lcfg))
# Habitat point-light "intensity" is in its own arbitrary unit; Cycles point
# lights are watts.  Scale so the room reads as normally lit rather than black.
SCALE = 60.0
n = 0
for _k, L in lj.get("lights", {}).items():
    if L.get("type") != "point":
        continue
    p = L["position"]
    pos = (float(p[0]), float(-p[2]), float(p[1]))     # Y-up -> Z-up
    d = bpy.data.lights.new(name=f"authored_{n}", type="POINT")
    d.energy = float(L.get("intensity", 1.0)) * SCALE
    d.color = tuple(float(c) for c in L.get("color", [1, 1, 1]))
    ob = bpy.data.objects.new(name=f"authored_{n}", object_data=d)
    ob.location = pos
    bpy.context.collection.objects.link(ob)
    n += 1
print(f"BLEND authored lights: {n}")

# --- group everything so the pipeline can find it by object_name ------------
for o in bpy.data.objects:
    o.name = o.name  # keep names stable
bpy.ops.wm.save_as_mainfile(filepath=target, compress=True)
print(f"BLEND wrote {target}  ({os.path.getsize(target)/1048576:.1f} MB)")
print(f"BLEND objects: {len([o for o in bpy.data.objects if o.type=='MESH'])} meshes, "
      f"{len([o for o in bpy.data.objects if o.type=='LIGHT'])} lights")
PY
