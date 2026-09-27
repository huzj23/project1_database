#!/usr/bin/env bash
# ===========================================================================
# Render the REFORMED setup:
#   A) indoor  -- scene's own 94 m^2 floor + the mahogany turntable + actor
#   B) outdoor -- the scene's own HDRI ground, NO synthetic plane at all
#
# Indoor: the object now rests on the scene's real floor instead of a 5.4 m^2
# patch.  The turntable sits on the floor of the open living area, and the actor
# is carried around it by friction (the physics rig already verified).
#
# Outdoor: the synthetic plane is DELETED.  The user's point was that the plane
# was ours, not the scene's -- so with the plane gone, the only ground is the
# HDRI's own.  The actor floats at its rest height because there is no collision
# surface, which is the honest trade: we cannot have both "no plane" and "the
# object rests on something" unless we give the actor a collision floor.
#
# So the outdoor render comes in two variants:
#   * "hdri_only"    - no plane, object placed at rest height (ground = HDRI's)
#   * "shadow_only"  - an invisible shadow catcher under the actor, so a contact
#                      shadow appears on the HDRI's ground while the ground the
#                      viewer sees is still the HDRI's
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_reformed"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PYEOF' 2>&1 | grep -E '^RF'
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
    print("RF", *a, flush=True)

R = os.path.join(WS, "models/backgrounds/replicad")
GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
DISC_R, DISC_T = 0.30, 0.022
FLOOR_Z = 0.0007

# ---------------------------------------------------------------------------
# A) INDOOR: scene's own floor + turntable
# ---------------------------------------------------------------------------
scratch = tempfile.mkdtemp(prefix="rf_in_")
scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
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
say(f"indoor room loaded, authored lights={n}")

# the scene's own floor as collision: 94.29 m^2, matching asset.yaml
FLOOR_C = (0.9515, -1.6675)
FLOOR_HX, FLOOR_HY = 3.6285, 6.4965
floor = kb.Cube(name="scene_floor", scale=(FLOOR_HX, FLOOR_HY, 0.05),
                position=(FLOOR_C[0], FLOOR_C[1], FLOOR_Z - 0.05),
                static=True, segmentation_id=1)
floor.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.52, 0.48, 1.0), roughness=0.7)
scene += floor
say(f"scene floor collision: {2*FLOOR_HX:.2f} x {2*FLOOR_HY:.2f} m = "
    f"{4*FLOOR_HX*FLOOR_HY:.2f} m^2 at z={FLOOR_Z}")

# turntable on the floor of the open living area
TX, TY = 1.00, -4.30
DZ = FLOOR_Z + DISC_T / 2.0
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
say(f"turntable on the scene floor, dark_wood applied={pb.apply_bpy_material(renderer, disc, mat)}")

meta = json.load(open(os.path.join(GSO, "data.json")))
b = meta["kwargs"]["bounds"]; rest = -b[0][2]
obj = kb.FileBasedObject(
    name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
    render_filename=os.path.join(GSO, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
    scale=1.0, position=(TX + 0.17, TY, FLOOR_Z + DISC_T + rest + 0.006),
    segmentation_id=2)
scene += obj

import pybullet as pbc
did = disc.linked_objects[sim]
oid = obj.linked_objects[sim]
pbc.changeDynamics(did, -1, lateralFriction=1.2)
pbc.changeDynamics(oid, -1, lateralFriction=1.2)

OMEGA, SUB = 0.9, 15
NFRAMES = 25
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
        say(f"  sim f{f:02d}: actor r={math.hypot(ap[0]-TX, ap[1]-TY):.3f} "
            f"z={ap[2]:.3f} angle={math.degrees(math.atan2(ap[1]-TY, ap[0]-TX)):+7.1f}")

# keyframe replay (Blender will not animate on its own)
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

cam = kb.PerspectiveCamera(focal_length=42.0, sensor_width=36.0)
cam.position = (TX + 0.95, TY - 1.15, 0.85)
cam.look_at((TX, TY, 0.10))
scene.camera = cam
out = renderer.render([0, 8, 16, 24], return_layers=("rgba",))
imgs = np.array(out["rgba"], copy=True)
for i, f in enumerate((0, 8, 16, 24)):
    cv2.imwrite(os.path.join(OUT, f"indoor_f{f:02d}.png"), imgs[i][..., :3][..., ::-1])
base = imgs[0][..., :3].astype(np.int16)
for i, f in enumerate((8, 16, 24), start=1):
    d = np.abs(imgs[i][..., :3].astype(np.int16) - base)
    say(f"  indoor f{f:02d} vs f00: changed px={int((d.max(axis=2)>3).sum())}")
say("indoor done")

# ---------------------------------------------------------------------------
# B) OUTDOOR: no synthetic plane; the HDRI's own ground is the ground
# ---------------------------------------------------------------------------
ENVS = [("german_town_street", "street / town"),
        ("autumn_park", "nature / park"),
        ("orlando_stadium", "sports / stadium")]

for env, label in ENVS:
    for variant in ("hdri_only", "shadow_only"):
        sc = tempfile.mkdtemp(prefix="rf_out_")
        scene2 = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                          frame_rate=24, step_rate=240, gravity=(0, 0, 0))
        r2 = Blender(scene2, sc, samples_per_pixel=48, use_denoising=True, verbose=True)
        s2 = PyBullet(scene2, sc)

        if variant == "shadow_only":
            # invisible to camera rays, but still receives the contact shadow
            gp = kb.Cube(name="shadow_catcher", scale=(60, 60, 0.1),
                         position=(0, 0, -0.1), static=True, segmentation_id=1)
            gp.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.9)
            scene2 += gp
            gp.linked_objects[r2].is_shadow_catcher = True

        pb.enable_hdri_file(r2, env, strength=1.0, bg_strength=1.0)

        m2 = json.load(open(os.path.join(GSO, "data.json")))
        b2 = m2["kwargs"]["bounds"]; rest2 = -b2[0][2]
        o2 = kb.FileBasedObject(
            name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
            render_filename=os.path.join(GSO, "visual_geometry.obj"),
            bounds=tuple(tuple(v) for v in b2), mass=m2["kwargs"]["mass"],
            scale=1.0, position=(0.0, 0.0, rest2), segmentation_id=2)
        scene2 += o2

        c2 = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
        c2.position = (0.9, -3.4, 1.15)
        c2.look_at((0.0, 0.0, 1.07))
        scene2.camera = c2
        o = r2.render([0], return_layers=("rgba",))
        im = np.array(o["rgba"], copy=True)[0][..., :3]
        cv2.imwrite(os.path.join(OUT, f"out_{env}__{variant}.png"), im[..., ::-1])
        say(f"outdoor {env} [{variant}] done")
PYEOF
