#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# THE ACTUAL FIX: get our plane out of the camera's view entirely.
#
# Measured facts (ballawley_park, camera at 1.15 m):
#     horizon in the HDRI               row 197
#     our visible plane starts at       row 333 (800 m) .. 449 (14 m)
#     => the plane covers 136..252 rows of the HDRI's own ground, which is the
#        "cover-up" the user sees.  It is NOT a brightness mismatch; the plane
#        simply hides the backdrop's ground.
#     the shadow catcher only altered 7 rows, i.e. it works correctly and is
#     transparent to camera rays -- so the visible variant is what covers.
#
# Therefore the fix is not to match the two grounds, and not to make the plane
# transparent: it is to LOWER THE PLANE below the point where the camera can see
# it, while keeping it under the actor so contact shadows still land.
#
# A camera at height H looking at a target slightly below H sees the plane's far
# edge at angle atan(H / half_extent) below the horizon.  Dropping the plane by d
# moves its edge to atan((H+d) / half_extent) -- larger, i.e. further down, out of
# frame.  So: keep the plane big, sink it, and drop the actor onto it.
#
# This sweep finds the sink depth at which the plane stops painting the backdrop.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_plane_sink"
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
    print("PS", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
ENV, ASSET, CAT = "ballawley_park", "grass_ground", "grass_textures"
CAM_H, FL = 1.15, 35.0
SENSOR_H = 36.0 / (16.0 / 9.0)
VFOV = 2 * math.degrees(math.atan(SENSOR_H / (2 * FL)))
HALF = 400.0
UVS = HALF / 2.857


def render(sink, with_actor):
    """sink: how far BELOW the actor's feet the plane's top surface sits."""
    scratch = tempfile.mkdtemp(prefix="ps_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    top = -sink
    ground = kb.Cube(name="ground", scale=(HALF, HALF, 0.1),
                     position=(0, 0, top - 0.1), static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
    scene += ground
    mat, info = pb.pbr_material(kb, ASSET, CAT, uv_scale=UVS)
    pb.apply_bpy_material(renderer, ground, mat)

    pb.enable_hdri_file(renderer, ENV, strength=1.0, bg_strength=1.0)

    if with_actor:
        meta = json.load(open(os.path.join(GSO, "data.json")))
        b = meta["kwargs"]["bounds"]; rest = -b[0][2]
        obj = kb.FileBasedObject(
            name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
            render_filename=os.path.join(GSO, "visual_geometry.obj"),
            bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
            scale=1.0, position=(0.0, 0.0, top + rest), segmentation_id=2)
        scene += obj

    cam = kb.PerspectiveCamera(focal_length=FL, sensor_width=36.0)
    cam.position = (0.9, -3.4, CAM_H)
    cam.look_at((0.0, 0.0, CAM_H - 0.08))
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    return np.array(out["rgba"], copy=True)[0][..., :3]


ref = render(0.0, False)                       # no actor, plane at 0
cv2.imwrite(os.path.join(OUT, "ref.png"), ref[..., ::-1])
h, w = ref.shape[:2]
col0 = ref[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
lum0 = 0.114 * col0[:, 0] + 0.587 * col0[:, 1] + 0.299 * col0[:, 2]
g0 = np.abs(np.diff(np.convolve(lum0, np.ones(9) / 9, mode="same")))
lo, hi = int(h * 0.20), int(h * 0.75)
hrow = lo + int(np.argmax(g0[lo:hi]))
say(f"{ENV}: horizon row {hrow}, vFOV {VFOV:.2f} deg, plane half {HALF} m")

# a no-plane reference, so "our plane is invisible" can be tested exactly
scratch = tempfile.mkdtemp(prefix="psn_")
scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
PyBullet(scene, scratch)
pb.enable_hdri_file(renderer, ENV, strength=1.0, bg_strength=1.0)
cam = kb.PerspectiveCamera(focal_length=FL, sensor_width=36.0)
cam.position = (0.9, -3.4, CAM_H)
cam.look_at((0.0, 0.0, CAM_H - 0.08))
scene.camera = cam
none = np.array(renderer.render([0], return_layers=("rgba",))["rgba"], copy=True)[0][..., :3]
cv2.imwrite(os.path.join(OUT, "no_plane.png"), none[..., ::-1])

say("")
say(f"{'sink_m':>8}{'first row plane paints':>26}{'rows covered':>14}{'visible?':>12}")
for sink in (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 20.0):
    img = render(sink, False)
    cv2.imwrite(os.path.join(OUT, f"sink_{sink:04.1f}.png"), img[..., ::-1])
    d = np.abs(img.astype(np.int16) - none.astype(np.int16))
    per_row = d.max(axis=(1, 2))
    changed = np.where(per_row > 4)[0]
    if len(changed) == 0:
        say(f"{sink:>8.1f}{'NONE':>26}{0:>14}{'invisible':>12}")
    else:
        say(f"{sink:>8.1f}{int(changed[0]):>26}{int((per_row>4).sum()):>14}{'VISIBLE':>12}")

say("")
say("goal: a sink depth where the plane becomes invisible, so the ground the")
say("viewer sees is the HDRI's own -- then drop the actor onto it and let a")
say("shadow catcher catch the contact shadow.")
PYEOF
