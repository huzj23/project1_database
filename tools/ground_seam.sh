#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Why does the ground still look pasted on?
#
# The HDRI is an equirectangular panorama: its lower half IS ground imagery, with
# the horizon at roughly 0 degrees of elevation.  Our synthetic plane is only 14 m
# across.  From a camera 1.15 m high its far edge sits about atan(1.15/7) = 9 deg
# BELOW the horizon, so a band of the panorama's OWN ground is visible between our
# plane's edge and the horizon.  Two grounds, different scale and brightness, with
# a hard edge between them.
#
# Fix: make the plane large enough that its far edge lands essentially ON the
# horizon, so the panorama's ground is never visible and the only boundary is the
# natural horizon line itself.
#
# This renders german_town_street at three plane sizes and MEASURES the seam, so
# the choice is evidence-based rather than "bigger looks better".
#   for each size, scan the centre column and find the row with the sharpest
#   vertical colour change between the horizon and the bottom of frame.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_ground_seam"
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
    print("GS", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
ENV = "german_town_street"
CAM_H = 1.15
# (half_extent_m, uv_scale) -- uv_scale kept proportional so texture DENSITY is
# constant; otherwise a bigger plane just stretches the same few tiles.
SIZES = [(7.0, 2.5), (40.0, 14.0), (150.0, 52.0)]

for half, uvs in SIZES:
    scratch = tempfile.mkdtemp(prefix="gs_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(half, half, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
    scene += ground
    mat, info = pb.pbr_material(kb, "asphalt_01", "asphalt_textures", uv_scale=uvs)
    ok = pb.apply_bpy_material(renderer, ground, mat)

    pb.enable_hdri_file(renderer, ENV, strength=0.9, bg_strength=1.0)
    key = kb.DirectionalLight(name="key", position=(-2.6, -1.2, 2.6), intensity=2.6)
    key.look_at((0, 0, 0.15))
    scene += key

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(0.0, 0.0, rest), segmentation_id=2)
    scene += obj

    # horizon-level camera so the horizon line is visible and measurable
    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = (0.9, -3.4, CAM_H)
    cam.look_at((0.0, 0.0, CAM_H - 0.10))
    scene.camera = cam

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0][..., :3]
    q = os.path.join(OUT, f"half{int(half):03d}.png")
    cv2.imwrite(q, img[..., ::-1])

    # measure: centre column, find sharpest vertical change in the lower 2/3
    h, w = img.shape[:2]
    col = img[:, int(w * 0.5) - 40:int(w * 0.5) + 40].mean(axis=1).astype(np.float32)
    grad = np.abs(np.diff(col, axis=0)).mean(axis=1)
    lo, hi = int(h * 0.35), int(h * 0.95)
    row = lo + int(np.argmax(grad[lo:hi]))
    # what angle below the horizon is that row?
    # camera looks slightly down; approximate using the vertical FOV
    vfov = 2 * math.degrees(math.atan(36.0 / (16.0 / 9.0) / (2 * 35.0)))
    below_h = (row / float(h) - 0.5) * vfov
    edge_deg = math.degrees(math.atan(CAM_H / half))
    say(f"plane {2*half:6.0f} m  uv={uvs:5.1f}  tex_ok={ok}  "
        f"sharpest edge at row {row} ({below_h:+.2f} deg from centre)  "
        f"| predicted plane edge {edge_deg:.2f} deg below horizon")

say("")
say("small plane  -> its far edge is many degrees below the horizon, so a band of")
say("                the panorama's OWN ground shows above it: two grounds + a seam")
say("large plane  -> edge lands essentially on the horizon, panorama ground hidden")
PYEOF
