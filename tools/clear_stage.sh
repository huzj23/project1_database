#!/usr/bin/env bash
# Clear the stage: re-export scene.blend WITHOUT the furniture around the drop point.
#
# The frame showed the teddy landing against a large black planter, with a white
# pillar occupying a third of the view.  Those are the obstructions to remove.
#
# Method: keep every prop whose footprint is farther than CLEAR_R from the drop
# point (1.00, -4.30); drop the rest.  The stage shell (walls/floor/stairs) is
# untouched, so the room still reads as a room -- which is what "not too empty"
# requires.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^CLEAR|^  '
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
target = os.path.join(OUT, "scene.blend")
BX, BY = 1.00, -4.30
CLEAR_R = 0.95          # remove only what physically blocks the sight line

scratch = tempfile.mkdtemp(prefix="cl_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))

kept, removed = 0, []
for inst in cfg.get("object_instances", []):
    tpl = inst["template_name"].split("/")[-1]
    glb = os.path.join(R, "objects", f"{tpl}.glb")
    if not os.path.isfile(glb):
        continue
    tr = inst.get("translation", [0, 0, 0])
    # habitat (x, y, z) -> blender (x, -z, y)
    ox, oy = float(tr[0]), float(-tr[2])
    if math.hypot(ox - BX, oy - BY) < CLEAR_R:
        removed.append((tpl, round(ox, 2), round(oy, 2)))
        continue
    b2 = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception:
        continue
    for o in [o for o in bpy.data.objects if o.name not in b2]:
        if o.parent is None:
            o.location = (o.location.x + ox, o.location.y + oy,
                          o.location.z + float(tr[1]))
    kept += 1

print(f"CLEAR kept {kept} props, removed {len(removed)} within {CLEAR_R} m of "
      f"({BX},{BY}):")
for t, x, y in sorted(removed):
    print(f"    {t:<40} at ({x},{y})")

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
joined = bpy.context.view_layer.objects.active
joined.name = "environment"
n_mat = len(joined.data.materials)
print(f"CLEAR joined: {len(joined.data.vertices)} verts, {n_mat} materials")

# authored ceiling lights, as before (铁律�?
lcfg = os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")
lj = json.load(open(lcfg))
coll = bpy.data.collections.new("authored_lighting")
bpy.context.scene.collection.children.link(coll)
n = 0
for _k, L in lj.get("lights", {}).items():
    if L.get("type") != "point":
        continue
    p = L["position"]
    d = bpy.data.lights.new(name=f"authored_{n}", type="POINT")
    d.energy = float(L.get("intensity", 1.0)) * 60.0
    d.color = tuple(float(c) for c in L.get("color", [1, 1, 1]))
    ob = bpy.data.objects.new(name=f"authored_{n}", object_data=d)
    ob.location = (float(p[0]), float(-p[2]), float(p[1]))
    coll.objects.link(ob)
    n += 1
print(f"CLEAR authored lights: {n}")

bpy.ops.object.select_all(action="DESELECT")
joined.select_set(True)
bpy.context.view_layer.objects.active = joined
bpy.ops.wm.save_as_mainfile(filepath=target, compress=True)
print(f"CLEAR wrote {target} ({os.path.getsize(target)/1048576:.1f} MB)")
PY

echo
echo "=== run x0.5 ==="
bash "$WS/tools/clean_run.sh" 2>&1 | tail -18
