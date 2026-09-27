#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Re-export scene.blend with everything JOINED into a single mesh object.
#
# Kubric's .blend import path asserts `len(bpy.context.selected_objects) == 1`,
# so an environment file with 136 separate meshes fails:
#     AssertionError  at blender.py:631 _add_asset
#
# The mentor's own environment confirms the expectation -- his basketball court
# asset.yaml records `source_mesh_objects: 969` but `runtime_mesh_objects: 1`,
# i.e. he joins the authored scene into one runtime object.  Joining preserves
# per-face material assignment, so the 123 materials survive.
#
# Lights are written to a SEPARATE collection and NOT selected, so the import
# still sees exactly one object while the authored ceiling lights stay in the
# file for the lighting stage (铁律四).
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^BLEND|^  '
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
target = os.path.join(OUT, "scene.blend")

scratch = tempfile.mkdtemp(prefix="bl2_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
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
print(f"BLEND props placed: {placed}")

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print(f"BLEND meshes before join: {len(meshes)}")

# apply transforms so the join bakes real world coordinates
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()

joined = bpy.context.view_layer.objects.active
joined.name = "environment"
joined.data.name = "environment_mesh"
n_mat = len(joined.data.materials)
print(f"BLEND joined -> '{joined.name}': {len(joined.data.vertices)} verts, "
      f"{len(joined.data.polygons)} faces, {n_mat} materials")

# keep only the joined mesh selectable; park lights in their own collection
lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
if not lights:
    lcfg = os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")
    lj = json.load(open(lcfg))
    SCALE = 60.0
    coll = bpy.data.collections.new("authored_lighting")
    bpy.context.scene.collection.children.link(coll)
    n = 0
    for _k, L in lj.get("lights", {}).items():
        if L.get("type") != "point":
            continue
        p = L["position"]
        d = bpy.data.lights.new(name=f"authored_{n}", type="POINT")
        d.energy = float(L.get("intensity", 1.0)) * SCALE
        d.color = tuple(float(c) for c in L.get("color", [1, 1, 1]))
        ob = bpy.data.objects.new(name=f"authored_{n}", object_data=d)
        ob.location = (float(p[0]), float(-p[2]), float(p[1]))
        coll.objects.link(ob)
        n += 1
    print(f"BLEND authored lights created: {n}")

# exactly one selectable object so Kubric's import assertion holds
bpy.ops.object.select_all(action="DESELECT")
joined.select_set(True)
bpy.context.view_layer.objects.active = joined

bpy.ops.wm.save_as_mainfile(filepath=target, compress=True)
print(f"BLEND wrote {target}  ({os.path.getsize(target)/1048576:.1f} MB)")
print(f"BLEND scene objects: {len(bpy.data.objects)} "
      f"(selectable meshes: {len([o for o in bpy.data.objects if o.type=='MESH'])})")
PY
