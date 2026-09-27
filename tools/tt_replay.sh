#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Mahogany turntable: replay the PyBullet trajectory as Blender KEYFRAMES.
#
# Why this step exists: rendering [0], [8], [16], [24] straight after stepping
# PyBullet produced four byte-identical PNGs (MD5 equal, pixel diff 0).  Blender
# had no animation of its own -- it was never told that anything moved -- so every
# frame rendered the same static pose.
#
# That is exactly the mentor's rule: "Never prescribe the simulated trajectory
# frame by frame; Blender only REPLAYS the validated trajectory."  The trajectory
# is still produced by the physics engine (contact + friction on the spinning
# disc); we only transcribe the result into keyframes so Blender can replay it.
#
# So: step the physics, record the actor's pose each video frame, insert those as
# location keyframes, THEN render.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_tt_replay"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PYEOF'
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
    print("TW", *a, flush=True)

R = os.path.join(WS, "models/backgrounds/replicad")
GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
DISC_R, DISC_T = 0.30, 0.022
VIDEO_FPS, PHYS_FPS = 16, 240
SUB = PHYS_FPS // VIDEO_FPS
NFRAMES = 25

scratch = tempfile.mkdtemp(prefix="ttr_")
scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=NFRAMES - 1,
                 frame_rate=VIDEO_FPS, step_rate=PHYS_FPS, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
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

TX, TY, TZ = 0.41, 0.17, 0.758
DZ = TZ + DISC_T / 2.0 + 0.002

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
say(f"disc material dark_wood applied={pb.apply_bpy_material(renderer, disc, mat)}")

meta = json.load(open(os.path.join(GSO, "data.json")))
b = meta["kwargs"]["bounds"]
rest = -b[0][2]
obj = kb.FileBasedObject(
    name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
    render_filename=os.path.join(GSO, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
    scale=1.0, position=(TX + 0.17, TY, TZ + DISC_T + rest + 0.008), segmentation_id=2)
scene += obj

import pybullet as pbc
did = disc.linked_objects[sim]
oid = obj.linked_objects[sim]
pbc.changeDynamics(did, -1, lateralFriction=1.2)
pbc.changeDynamics(oid, -1, lateralFriction=1.2)

# --- simulate, recording the pose of BOTH bodies each video frame ----------
OMEGA = 0.9
traj_actor, traj_disc = [], []
for f in range(NFRAMES):
    for _s in range(SUB):
        _cp, cq = pbc.getBasePositionAndOrientation(did)
        pbc.resetBasePositionAndOrientation(did, [TX, TY, DZ], cq)
        pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, OMEGA])
        pbc.stepSimulation()
    ap, aq = pbc.getBasePositionAndOrientation(oid)
    dp, dq = pbc.getBasePositionAndOrientation(did)
    traj_actor.append((ap, aq))
    traj_disc.append((dp, dq))
    if f % 6 == 0:
        say(f"sim frame {f:02d}: actor r={math.hypot(ap[0]-TX, ap[1]-TY):.3f} "
            f"angle={math.degrees(math.atan2(ap[1]-TY, ap[0]-TX)):+7.1f} deg")

# --- transcribe into Blender keyframes (the replay step) -------------------
say("inserting keyframes from the physics trajectory")
for f, ((ap, aq), (dp, dq)) in enumerate(zip(traj_actor, traj_disc)):
    bpy.context.scene.frame_set(f)          # kb.Scene has no frame_set
    ao = obj.linked_objects[renderer]
    do = disc.linked_objects[renderer]
    # Kubric objects carry a visual transform; only the base pose is keyframed
    ao.location = ap
    ao.rotation_mode = "QUATERNION"
    ao.rotation_quaternion = (aq[3], aq[0], aq[1], aq[2])
    ao.keyframe_insert("location", frame=f)
    ao.keyframe_insert("rotation_quaternion", frame=f)
    do.rotation_mode = "QUATERNION"
    do.rotation_quaternion = (dq[3], dq[0], dq[1], dq[2])
    do.keyframe_insert("rotation_quaternion", frame=f)

cam = kb.PerspectiveCamera(focal_length=48.0, sensor_width=36.0)
cam.position = (TX + 0.50, TY - 0.62, TZ + 0.40)
cam.look_at((TX, TY, TZ + 0.04))
scene.camera = cam

WANT = [0, 8, 16, 24]
out = renderer.render(WANT, return_layers=("rgba",))
imgs = np.array(out["rgba"], copy=True)
for i, f in enumerate(WANT):
    cv2.imwrite(os.path.join(OUT, f"replay_f{f:02d}.png"), imgs[i][..., :3][..., ::-1])
    say(f"wrote replay_f{f:02d}.png")

# prove the frames now actually differ
base = imgs[0][..., :3].astype(np.int16)
for i, f in enumerate(WANT[1:], start=1):
    d = np.abs(imgs[i][..., :3].astype(np.int16) - base)
    say(f"f{f:02d} vs f00: max={d.max()} mean={d.mean():.2f} changed={int((d.max(axis=2)>3).sum())}")
PYEOF
