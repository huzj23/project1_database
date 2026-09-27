#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DECISIVE: exactly which rows does our plane occupy, and is the shadow catcher
# really invisible to the camera?
#
# Method: render the SAME scene with and without a ground plane, no actor.  Any
# row where the two images differ is a row our plane is painting over.  The first
# such row is our plane's far edge; everything above it is the HDRI's own ground.
# That band -- HDRI ground above our plane's edge -- IS the seam.
#
# This also settles whether the shadow catcher works: a true shadow catcher is
# invisible to camera rays, so with no actor present it must match "no ground"
# EXACTLY.  If it does not, the shadow catcher is still painting pixels.
#
# Variants: no ground / visible 14 m / 120 m / 800 m / shadow-catcher 120 m / 800 m
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_plane_rows"
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
    print("PR", *a, flush=True)

ENV, ASSET, CAT = "ballawley_park", "grass_ground", "grass_textures"
CAM_H, FL = 1.15, 35.0
SENSOR_H = 36.0 / (16.0 / 9.0)
VFOV = 2 * math.degrees(math.atan(SENSOR_H / (2 * FL)))

VARIANTS = [
    ("none",         None,  False),
    ("vis_14m",      7.0,   False),
    ("vis_120m",     60.0,  False),
    ("vis_800m",     400.0, False),
    ("catch_120m",   60.0,  True),
    ("catch_800m",   400.0, True),
]


def render(half, catcher):
    scratch = tempfile.mkdtemp(prefix="pr_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    if half is not None:
        ground = kb.Cube(name="ground", scale=(half, half, 0.1), position=(0, 0, -0.1),
                         static=True, segmentation_id=1)
        ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
        scene += ground
        uv = half / 2.857                    # constant texture density
        mat, info = pb.pbr_material(kb, ASSET, CAT, uv_scale=uv)
        pb.apply_bpy_material(renderer, ground, mat)
        if catcher:
            go = ground.linked_objects[renderer]
            go.is_shadow_catcher = True
            say(f"  is_shadow_catcher set on {go.name} -> {go.is_shadow_catcher}")

    pb.enable_hdri_file(renderer, ENV, strength=1.0, bg_strength=1.0)
    cam = kb.PerspectiveCamera(focal_length=FL, sensor_width=36.0)
    cam.position = (0.9, -3.4, CAM_H)
    cam.look_at((0.0, 0.0, CAM_H - 0.08))
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    return np.array(out["rgba"], copy=True)[0][..., :3]


imgs = {}
for name, half, catcher in VARIANTS:
    imgs[name] = render(half, catcher)
    cv2.imwrite(os.path.join(OUT, f"{name}.png"), imgs[name][..., ::-1])

h, w = imgs["none"].shape[:2]
ref = imgs["none"].astype(np.int16)
say(f"env={ENV}  camera h={CAM_H}  vFOV={VFOV:.2f} deg  image {w}x{h}")
say("")
say(f"{'variant':<12}{'first row our plane paints':>28}{'rows covered':>14}{'as angle below horizon':>24}")

# where is the horizon?  it is where the HDRI's sky meets the HDRI's ground.
# find it as the biggest change in the no-ground image.
col0 = ref[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
lum0 = 0.114 * col0[:, 0] + 0.587 * col0[:, 1] + 0.299 * col0[:, 2]
g0 = np.abs(np.diff(np.convolve(lum0, np.ones(9) / 9, mode="same")))
lo, hi = int(h * 0.20), int(h * 0.75)
hrow = lo + int(np.argmax(g0[lo:hi]))
say(f"horizon in the HDRI (no-ground render) = row {hrow}")
say("")

for name, half, catcher in VARIANTS:
    if name == "none":
        continue
    d = np.abs(imgs[name].astype(np.int16) - ref)
    per_row = d.max(axis=(1, 2))
    changed = np.where(per_row > 4)[0]
    if len(changed) == 0:
        say(f"{name:<12}{'NONE - invisible':>28}{0:>14}{'-':>24}")
        continue
    first = int(changed[0])
    covered = int((per_row > 4).sum())
    deg = (first - hrow) / float(h) * VFOV
    say(f"{name:<12}{first:>28}{covered:>14}{deg:>+23.2f}d")

say("")
say("A shadow catcher must report NONE - invisible, because it is transparent to")
say("camera rays.  Anything else means it is still painting pixels.")
say("'first row' is where OUR ground takes over; the HDRI's own ground is visible")
say("from the horizon down to that row -- that band is the seam.")
PYEOF
