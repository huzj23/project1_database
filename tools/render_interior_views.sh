#!/usr/bin/env bash
# INTERIOR eye-level views of the furnished ReplicaCAD apartment.
#
# The dollhouse renders answered "is it furnished" -- it is.  This answers the
# real question: does it look like somewhere a person could be, at human height,
# with everyday objects around.  Several viewpoints so one bad angle cannot
# mislead the judgement.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scene_interior"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^IN|^  '
import sys, os, json, tempfile
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy, cv2

R = os.path.join(WS, "models/backgrounds/replicad")
STAGE = os.path.join(R, "stages/frl_apartment_stage.glb")
SJ = os.path.join(R, "configs/scenes/apt_0.scene_instance.json")

scratch = tempfile.mkdtemp(prefix="in_")
scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)

bpy.ops.import_scene.gltf(filepath=STAGE)
print("IN stage loaded")

cfg = json.load(open(SJ))
props = []
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
    props.append(tpl)
print(f"IN props placed: {len(props)}")

# where is the furniture actually clustered?
lo = np.array([1e18]*3); hi = np.array([-1e18]*3)
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    nm = o.name.lower()
    if not nm.startswith("frl_apartment_") or "floor" in nm or "wall" in nm or "door" in nm:
        continue
    mw = np.array(o.matrix_world)
    loc = np.array([list(c) for c in o.bound_box], dtype=float)
    w = loc @ mw[:3, :3].T + mw[:3, 3]
    lo = np.minimum(lo, w.min(axis=0)); hi = np.maximum(hi, w.max(axis=0))
centre = (lo + hi) / 2.0
print(f"IN furniture bbox centre=({centre[0]:.2f},{centre[1]:.2f},{centre[2]:.2f}) "
      f"span={np.round(hi-lo,2).tolist()}")

# neutral daylight-ish lighting so we judge the SCENE, not our light rig
renderer._set_ambient_light_color((0.75, 0.75, 0.78, 1.0))
renderer._set_background_color((0.62, 0.70, 0.82, 1.0))
sun = kb.DirectionalLight(name="sun", position=(centre[0]+4, centre[1]-4, centre[2]+6),
                          intensity=3.0)
sun.look_at((float(centre[0]), float(centre[1]), 0.4)); scene += sun
fill = kb.RectAreaLight(name="fill", position=(centre[0]-3, centre[1]+1.5, 2.4),
                        intensity=340.0, width=5.0, height=3.0)
fill.look_at((float(centre[0]), float(centre[1]), 0.5)); scene += fill

VIEWS = [
    ("A_eye_level",  (2.6, -3.4, 1.55), (float(centre[0]), float(centre[1]), 0.55)),
    ("B_corner_wide", (4.0, -5.2, 1.70), (float(centre[0]), float(centre[1]), 0.60)),
    ("C_low_angle",  (1.2, -4.6, 0.95), (float(centre[0]), float(centre[1]), 0.70)),
]
for tag, pos, aim in VIEWS:
    cam = kb.PerspectiveCamera(focal_length=32.0, sensor_width=36.0)
    cam.position = pos
    cam.look_at(aim)
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"  wrote {p}  cam={tuple(round(v,2) for v in pos)}")
PY
