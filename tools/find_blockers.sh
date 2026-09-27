#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Clear a viewing corridor by DELETING the furniture that blocks it.
#
# No pipeline changes: instead we make the scene cooperate.
#   1. pin the subject to the measured best-clearance point (1.00, -4.30)
#   2. choose a camera geometry from the line-of-sight survey
#   3. ray-cast camera -> subject along the whole fall, and record EVERY prop
#      that intercepts the ray
#   4. write those prop names to a blocklist for the scene exporter
#
# Step 3 reports object names, so the removal is targeted rather than "delete
# everything nearby".
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" <<'PY' 2>&1 | grep -E '^CLR|^  '
import sys, os, json, tempfile, math
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
from mathutils import Vector

R = os.path.join(WS, "models/backgrounds/replicad")
scratch = tempfile.mkdtemp(prefix="clr_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
sim = PyBullet(scene, scratch)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))

# remember which objects came from which prop, so a blocker can be named
prop_of = {}
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
    new = [o for o in bpy.data.objects if o.name not in b2]
    tr = inst.get("translation", [0, 0, 0])
    for o in new:
        if o.parent is None:
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))
        prop_of[o.name] = tpl
print(f"CLR props in scene: {len(set(prop_of.values()))}")

dg = bpy.context.evaluated_depsgraph_get()

BX, BY, FLOOR_Z = 1.00, -4.30, 0.0007
STANDOFF = 2.05
ELEV = 28.0          # from the survey: 17/24 clear, still a natural view
best_az, best_hits, best_cam = None, None, None
for az in range(0, 360, 10):
    el, ar = math.radians(ELEV), math.radians(az)
    cam = Vector((BX + STANDOFF * math.cos(el) * math.cos(ar),
                  BY + STANDOFF * math.cos(el) * math.sin(ar),
                  FLOOR_Z + STANDOFF * math.sin(el)))
    if not (-2.60 <= cam.x <= 4.50 and -8.10 <= cam.y <= 4.80):
        continue
    hits = set()
    for z in (0.05, 0.35, 0.70, 1.05):        # the whole fall
        tgt = Vector((BX, BY, z))
        d = tgt - cam
        ok, loc, nrm, idx, obj, m = bpy.context.scene.ray_cast(
            dg, cam, d.normalized(), distance=max(d.length - 0.05, 0.01))
        if ok and obj is not None:
            hits.add(prop_of.get(obj.name, obj.name))
    if best_hits is None or len(hits) < len(best_hits):
        best_hits, best_az, best_cam = hits, az, cam

print(f"CLR best azimuth {best_az} deg  camera=({best_cam.x:.2f},{best_cam.y:.2f},{best_cam.z:.2f})")
print(f"CLR blockers to delete ({len(best_hits)}):")
for b in sorted(best_hits):
    print(f"    {b}")

out = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/configs/_clear_view.json")
json.dump({"region_xy": [BX, BY], "azimuth_deg": best_az, "elevation_deg": ELEV,
           "standoff_m": STANDOFF, "delete_props": sorted(best_hits)},
          open(out, "w"), indent=2)
print(f"CLR wrote {out}")
PY
