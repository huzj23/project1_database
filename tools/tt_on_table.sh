#!/usr/bin/env bash
# ===========================================================================
# Turntable BACK ON THE TABLE, with the scene's real floor as collision.
#
# Placement (restored to the frozen decision):
#   table   frl_apartment_table_01 at blender (0.41, 0.17), top z = 0.758
#   disc    radius 0.30 m, thickness 0.022 m, sitting ON the table top
#   actor   starts 0.17 m from the disc axis, carried by friction
#
# The table top is measured from the imported mesh, not hard-coded, so the disc
# cannot end up floating above or sunk into it.
#
# The 94.29 m^2 scene floor is present as collision (the requested reform), so if
# anything ever falls off the table it lands on the room's real floor rather than
# on a patch of ours.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_tt_table"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PYEOF' 2>&1 | grep -E '^TB'
import sys, os, json, tempfile, math
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

def say(*a):
    print("TB", *a, flush=True)

R = os.path.join(WS, "models/backgrounds/replicad")
GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
DISC_R, DISC_T = 0.30, 0.022
FLOOR_Z = 0.0007

scratch = tempfile.mkdtemp(prefix="tb_")
scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=24,
                 frame_rate=16, step_rate=240, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=64, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
for inst in cfg.get("object_instances", []):
    tpl = inst["template_name"].split("/")[-1]
    glb = os.path.join(R, "objects", f"{tpl}.glb")
    if not os.path.isfile(glb):
        continue
    before = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception:
        continue
    tr = inst.get("translation", [0, 0, 0])
    for o in [o for o in bpy.data.objects if o.name not in before]:
        if o.parent is None:
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))

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
say(f"room loaded, authored lights={n}")

# the scene's own floor, as collision (the requested reform)
floor = kb.Cube(name="scene_floor", scale=(3.6285, 6.4965, 0.05),
                position=(0.9515, -1.6675, FLOOR_Z - 0.05),
                static=True, segmentation_id=1)
floor.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.52, 0.48, 1.0), roughness=0.7)
scene += floor

# --- measure the table top from its real mesh -----------------------------
best = None
for o in bpy.data.objects:
    if o.type != "MESH" or "table_01" not in o.name.lower():
        continue
    mw = np.array(o.matrix_world)
    bb = np.array([list(c) for c in o.bound_box], dtype=float)
    w = bb @ mw[:3, :3].T + mw[:3, 3]
    span = w.max(axis=0) - w.min(axis=0)
    top = float(w[:, 2].max())
    cx = (w[:, 0].min() + w[:, 0].max()) / 2.0
    cy = (w[:, 1].min() + w[:, 1].max()) / 2.0
    if best is None or span[0] * span[1] > best[0]:
        best = (span[0] * span[1], o.name, cx, cy, top, span)

if best is None:
    say("TABLE NOT FOUND -- aborting")
    raise SystemExit(1)
_s, tname, TX, TY, TZ, span = best
say(f"table: {tname}")
say(f"  centre=({TX:.3f},{TY:.3f})  top z={TZ:.4f}  span={np.round(span,3).tolist()}")
say(f"  disc dia={2*DISC_R:.2f} m vs table {max(span[0],span[1]):.2f} m "
    f"-> fits={bool(2*DISC_R < max(span[0],span[1]))}")

# --- collision under the table so the disc has something to rest on --------
table_top = kb.Cube(name="table_top", scale=(span[0]/2.0, span[1]/2.0, 0.02),
                    position=(TX, TY, TZ - 0.02), static=True, segmentation_id=1)
scene += table_top

# --- disc ON the table ----------------------------------------------------
DZ = TZ + DISC_T / 2.0
disc = kb.FileBasedObject(
    name="turntable", asset_id="turntable",
    simulation_filename=os.path.join(TT, "collision/model.urdf"),
    render_filename=os.path.join(TT, "visual/model.obj"),
    scale=(1.0, 1.0, 1.0), static=False,
    position=(TX, TY, DZ), segmentation_id=3)
disc.material = kb.PrincipledBSDFMaterial(color=(0.30, 0.12, 0.06, 1.0),
                                          roughness=0.30, metallic=0.0)
scene += disc
mat, info = pb.pbr_material(kb, "dark_wood", "wood_textures", uv_scale=1.6)
say(f"disc on table, dark_wood applied={pb.apply_bpy_material(renderer, disc, mat)}")

meta = json.load(open(os.path.join(GSO, "data.json")))
b = meta["kwargs"]["bounds"]; rest = -b[0][2]
obj = kb.FileBasedObject(
    name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
    render_filename=os.path.join(GSO, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
    scale=1.0, position=(TX + 0.17, TY, DZ + DISC_T / 2.0 + rest + 0.005),
    segmentation_id=2)
scene += obj

import pybullet as pbc
did = disc.linked_objects[sim]
oid = obj.linked_objects[sim]
pbc.changeDynamics(did, -1, lateralFriction=1.2)
pbc.changeDynamics(oid, -1, lateralFriction=1.2)

OMEGA, SUB, NFRAMES = 0.9, 15, 25
traj_a, traj_d = [], []
for f in range(NFRAMES):
    for _s in range(SUB):
        _cp, cq = pbc.getBasePositionAndOrientation(did)
        pbc.resetBasePositionAndOrientation(did, [TX, TY, DZ], cq)
        pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, OMEGA])
        pbc.stepSimulation()
    ap, aq = pbc.getBasePositionAndOrientation(oid)
    dp, dq = pbc.getBasePositionAndOrientation(did)
    traj_a.append((ap, aq)); traj_d.append((dp, dq))
    if f % 8 == 0:
        say(f"  sim f{f:02d}: r={math.hypot(ap[0]-TX, ap[1]-TY):.3f} z={ap[2]:.4f} "
            f"(table top {TZ:.4f}) angle={math.degrees(math.atan2(ap[1]-TY, ap[0]-TX)):+7.1f}")

scene.frame_end = NFRAMES - 1
for f, ((ap, aq), (dp, dq)) in enumerate(zip(traj_a, traj_d)):
    bpy.context.scene.frame_set(f)
    ao = obj.linked_objects[renderer]; do = disc.linked_objects[renderer]
    ao.location = ap
    ao.rotation_mode = "QUATERNION"
    ao.rotation_quaternion = (aq[3], aq[0], aq[1], aq[2])
    ao.keyframe_insert("location", frame=f)
    ao.keyframe_insert("rotation_quaternion", frame=f)
    do.rotation_mode = "QUATERNION"
    do.rotation_quaternion = (dq[3], dq[0], dq[1], dq[2])
    do.keyframe_insert("rotation_quaternion", frame=f)
say("  keyframes inserted")

cam = kb.PerspectiveCamera(focal_length=50.0, sensor_width=36.0)
cam.position = (TX + 0.52, TY - 0.66, TZ + 0.42)
cam.look_at((TX, TY, TZ + 0.05))
scene.camera = cam
out = renderer.render([0, 8, 16, 24], return_layers=("rgba",))
imgs = np.array(out["rgba"], copy=True)
for i, f in enumerate((0, 8, 16, 24)):
    cv2.imwrite(os.path.join(OUT, f"table_f{f:02d}.png"), imgs[i][..., :3][..., ::-1])
base = imgs[0][..., :3].astype(np.int16)
for i, f in enumerate((8, 16, 24), start=1):
    d = np.abs(imgs[i][..., :3].astype(np.int16) - base)
    say(f"  f{f:02d} vs f00: changed px={int((d.max(axis=2)>3).sum())}")
say(f"wrote 4 frames to {OUT}")
PYEOF
