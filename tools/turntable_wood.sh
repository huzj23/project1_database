#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Turntable with a MAHOGANY-LIKE wood disc, sitting on an INDOOR TABLE.
#
# Two changes from the bare test rig:
#   1. MATERIAL.  A plain grey disc reads as a piece of lab equipment.  A polished
#      hardwood disc is what a turntable actually looks like in a room, so the
#      disc gets a real veneer texture (cherry_veneer is the reddish hardwood
#      closest to mahogany; american_walnut is the darker alternative).
#   2. PLACE.  The disc is moved onto a real table top found in the ReplicaCAD
#      apartment rather than standing on the floor, so the whole rig belongs to
#      the room.
#
# The table's top surface is measured from its actual bounding box, so the disc
# sits ON the table rather than floating or intersecting it.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_turntable_wood"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^TW|^  '
import sys, os, json, tempfile, glob, math
WS, OUT = sys.argv[1], sys.argv[2]
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
import bpy, cv2
from mathutils import Vector

R = os.path.join(WS, "models/backgrounds/replicad")
GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
DISC_R, DISC_T = 0.30, 0.022

scratch = tempfile.mkdtemp(prefix="tw_")
scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=64, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)

# --- the room -------------------------------------------------------------
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

# authored lighting (铁律�?
lj = json.load(open(os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")))
n = 0
for _k, L in lj.get("lights", {}).items():
    if L.get("type") != "point":
        continue
    p = L["position"]
    scene += kb.PointLight(name=f"auth{n}",
                           position=(float(p[0]), float(-p[2]), float(p[1])),
                           intensity=float(L.get("intensity", 1.0)) * 60.0,
                           color=tuple(float(c) for c in L.get("color", [1, 1, 1])))
    n += 1
renderer._set_ambient_light_color((0.50, 0.50, 0.53, 1.0))
renderer._set_background_color((0.60, 0.68, 0.80, 1.0))
print(f"TW room loaded, authored lights={n}")

# --- find a table to put the disc on --------------------------------------
best = None
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    if "table" not in o.name.lower():
        continue
    mw = np.array(o.matrix_world)
    loc = np.array([list(c) for c in o.bound_box], dtype=float)
    w = loc @ mw[:3, :3].T + mw[:3, 3]
    span = w.max(axis=0) - w.min(axis=0)
    top = float(w[:, 2].max())
    cx, cy = (w[:, 0].min() + w[:, 0].max()) / 2, (w[:, 1].min() + w[:, 1].max()) / 2
    # want a table top wide enough for a 1.1 m disc, and not a giant counter
    area = span[0] * span[1]
    if top < 0.5 or top > 1.1:
        continue
    if max(span[0], span[1]) < 2 * DISC_R + 0.15:
        continue
    score = area
    if best is None or score > best[0]:
        best = (score, o.name, cx, cy, top, span)

if best is None:
    print("TW no suitable table found -- falling back to the floor")
    TX, TY, TZ = 0.9, -4.05, 0.0
else:
    _s, tname, TX, TY, TZ, span = best
    print(f"TW table: {tname}")
    print(f"TW   centre=({TX:.2f},{TY:.2f})  top z={TZ:.3f}  span={np.round(span,2).tolist()}")

# --- disc on the table ----------------------------------------------------
disc = kb.FileBasedObject(
    name="turntable", asset_id="turntable",
    simulation_filename=os.path.join(TT, "collision/model.urdf"),
    render_filename=os.path.join(TT, "visual/model.obj"),
    scale=(1.0, 1.0, 1.0), static=False,
    position=(TX, TY, TZ + DISC_T / 2.0 + 0.002), segmentation_id=3)
disc.material = kb.PrincipledBSDFMaterial(color=(0.32, 0.12, 0.06, 1.0),
                                          roughness=0.28, metallic=0.0)
scene += disc
mat, info = pb.pbr_material(kb, "cherry_veneer", "wood_textures", uv_scale=1.6)
if pb.apply_bpy_material(renderer, disc, mat):
    print("TW disc material: cherry_veneer (reddish hardwood, mahogany-like)")
else:
    print("TW disc material: FALLBACK flat colour (texture apply failed)")

# --- actor on the disc ----------------------------------------------------
meta = json.load(open(os.path.join(GSO, "data.json")))
b = meta["kwargs"]["bounds"]; rest = -b[0][2]
obj = kb.FileBasedObject(
    name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
    render_filename=os.path.join(GSO, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
    scale=1.0, position=(TX + 0.30, TY, TZ + DISC_T + rest + 0.01), segmentation_id=2)
scene += obj

# --- spin the disc physically, then render a few frames -------------------
did = disc.linked_objects[sim]
oid = obj.linked_objects[sim]
import pybullet as pbc
pbc.changeDynamics(did, -1, lateralFriction=1.2)
pbc.changeDynamics(oid, -1, lateralFriction=1.2)

OMEGA = 0.9
SUB = 15                                   # 240 Hz / 16 fps
FRAMES = [0, 12, 24, 36]
frames = {}
for s in range(36 * SUB + 1):
    cp, cq = pbc.getBasePositionAndOrientation(did)
    pbc.resetBasePositionAndOrientation(did, [TX, TY, TZ + DISC_T / 2.0 + 0.002], cq)
    pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, OMEGA])
    pbc.stepSimulation()
    if s % SUB == 0:
        f = s // SUB
        if f in FRAMES:
            ap, _ = pbc.getBasePositionAndOrientation(oid)
            frames[f] = (float(ap[0]), float(ap[1]), float(ap[2]))

for f, (ax, ay, az) in sorted(frames.items()):
    r = math.hypot(ax - TX, ay - TY)
    print(f"TW frame {f:02d}: actor=({ax:.3f},{ay:.3f},{az:.3f})  r={r:.3f}  "
          f"angle={math.degrees(math.atan2(ay - TY, ax - TX)):+.1f} deg")

# render the mid frame so the rig can be seen
cam = kb.PerspectiveCamera(focal_length=42.0, sensor_width=36.0)
cam.position = (TX + 0.95, TY - 1.05, TZ + 0.72)
cam.look_at((TX, TY, TZ + 0.10))
scene.camera = cam
out = renderer.render([0], return_layers=("rgba",))
img = np.array(out["rgba"], copy=True)[0]
cv2.imwrite(os.path.join(OUT, "turntable_wood_table.png"), img[..., :3][..., ::-1])
print(f"TW wrote {OUT}/turntable_wood_table.png")
PY
