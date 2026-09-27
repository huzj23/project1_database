#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Compute which camera positions have a CLEAR LINE OF SIGHT to the subject.
#
# Why offline: the camera is chosen before the environment is loaded, so the
# pipeline cannot ray-cast against the room at that point.  But the room never
# changes, so the clear directions can be measured once and recorded in the map
# asset -- which also keeps the choice reproducible and auditable.
#
# Method: put the subject at the support-region centre, then for every azimuth on
# a ring at the required stand-off, cast a ray from the camera toward the subject.
# If anything is hit before reaching it, that azimuth is occluded.  Repeat at
# several elevations, because much of the furniture is below 1 m and a higher
# camera can simply look over it.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^LOS|^  '
import sys, os, json, tempfile, math
WS, REPO = sys.argv[1], sys.argv[2]
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
scratch = tempfile.mkdtemp(prefix="los_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
sim = PyBullet(scene, scratch)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
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
print("LOS room loaded")

dg = bpy.context.evaluated_depsgraph_get()
BX, BY, FLOOR_Z = 1.00, -4.30, 0.0007
SUBJ = Vector((BX, BY, FLOOR_Z + 0.10))          # the actor's centre when resting
STANDOFF = 2.05

def blocked(cam, tgt):
    d = tgt - cam
    dist = d.length
    hit, loc, nrm, idx, obj, m = bpy.context.scene.ray_cast(
        dg, cam, d.normalized(), distance=max(dist - 0.05, 0.01))
    return bool(hit), (obj.name if hit else None)

print(f"LOS subject at ({BX:.2f},{BY:.2f})  standoff {STANDOFF} m")
print(f"LOS {'elev':>5} {'azim':>5}  clear?  first blocker")
best = []
for elev in (12, 20, 28, 36, 45):
    row = []
    for az in range(0, 360, 15):
        el = math.radians(elev); ar = math.radians(az)
        cam = Vector((BX + STANDOFF * math.cos(el) * math.cos(ar),
                      BY + STANDOFF * math.cos(el) * math.sin(ar),
                      FLOOR_Z + STANDOFF * math.sin(el)))
        # must stay inside the room box
        if not (-2.60 <= cam.x <= 4.50 and -8.10 <= cam.y <= 4.80):
            row.append("OUT")
            continue
        b, who = blocked(cam, SUBJ)
        row.append("BLK" if b else "ok ")
        if not b:
            best.append((elev, az, cam.x, cam.y, cam.z))
    print(f"LOS {elev:>5}   " + " ".join(row))

if best:
    # prefer the widest contiguous run of clear azimuths at the best elevation
    from collections import defaultdict
    by_elev = defaultdict(list)
    for e, a, *_ in best:
        by_elev[e].append(a)
    print("LOS clear azimuth counts per elevation:")
    for e in sorted(by_elev):
        print(f"    elev {e:>3}: {len(by_elev[e]):>2} of 24   {sorted(by_elev[e])}")
    e, a, x, y, z = best[0]
    print(f"LOS example clear camera: elev={e} az={a} pos=({x:.2f},{y:.2f},{z:.2f})")
else:
    print("LOS no clear camera found -- region is fully occluded")
PY
