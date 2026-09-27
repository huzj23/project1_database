#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# FINAL: mahogany-disc turntable on an indoor table.
#
# The four-way comparison settled the material question with measurements rather
# than a guess:
#     cherry_veneer           R/B 1.40  grain 14.8   too pale
#     american_walnut_veneer  R/B 1.05  grain 57.2   too pale / grey
#     dark_wood               R/B 2.00  grain 49.8   <-- reads as mahogany
# so dark_wood is used here.
#
# (The tint attempt in the comparison did nothing: the veneer's image texture is
# wired into Base Color and overrides a plain default_value, so tinting has to go
# through a Mix node.  Not needed now that dark_wood already measures correctly.)
#
# Also rendered: four frames through the spin, so the disc's rotation AND the
# actor being carried around it are both visible.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_tt_final"
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
VIDEO_FPS, PHYS_FPS, SECONDS = 16, 240, 3.0
SUB = PHYS_FPS // VIDEO_FPS

scratch = tempfile.mkdtemp(prefix="ttf_")
scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                 frame_rate=VIDEO_FPS, step_rate=PHYS_FPS, gravity=(0, 0, -9.81))
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

TX, TY, TZ = 0.41, 0.17, 0.758       # frl_apartment_table_01 top
DZ = TZ + DISC_T / 2.0 + 0.002
say(f"table top z={TZ:.3f}  disc centre z={DZ:.3f}")

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

OMEGA = 0.9
WANT = [0, 8, 16, 24]
seen = {}
for s in range(24 * SUB + 1):
    _cp, cq = pbc.getBasePositionAndOrientation(did)
    pbc.resetBasePositionAndOrientation(did, [TX, TY, DZ], cq)
    pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, OMEGA])
    pbc.stepSimulation()
    if s % SUB == 0:
        f = s // SUB
        if f in WANT:
            ap, _ = pbc.getBasePositionAndOrientation(oid)
            seen[f] = (float(ap[0]), float(ap[1]), float(ap[2]))

for f, (ax, ay, az) in sorted(seen.items()):
    r = math.hypot(ax - TX, ay - TY)
    say(f"frame {f:02d}: actor r={r:.3f} angle={math.degrees(math.atan2(ay-TY, ax-TX)):+7.1f} deg  "
        f"z={az:.3f}")

cam = kb.PerspectiveCamera(focal_length=48.0, sensor_width=36.0)
cam.position = (TX + 0.50, TY - 0.62, TZ + 0.40)
cam.look_at((TX, TY, TZ + 0.04))
scene.camera = cam

for f in WANT:
    out = renderer.render([f], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0][..., :3]
    cv2.imwrite(os.path.join(OUT, f"mahogany_f{f:02d}.png"), img[..., ::-1])
say(f"wrote {len(WANT)} frames to {OUT}")
PYEOF
