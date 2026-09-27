#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Decisive test: is our ground plane even visible?
#
# Plane size turned out not to matter (the step stayed at +44..+52 from 14 m to
# 800 m), so "too small a plane" is NOT the fault.  That leaves a more basic
# question: is our synthetic plane showing up in the picture at all, or are we
# looking straight at the panorama's own ground and mistaking its internal
# brightness gradient for a seam?
#
# Test: paint the plane pure MAGENTA.  Nothing in nature is magenta, so if the
# lower half of the frame is not magenta then our plane is not what the viewer
# sees down there.
#
# Three renders: no plane, normal plane, magenta plane.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_ground_probe"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PYEOF'
import sys, os, json, tempfile
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
    print("GP", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
ENV, ASSET, CAT = "german_town_street", "asphalt_01", "asphalt_textures"
CAM_H, HALF, UVS = 1.15, 60.0, 21.0


def render(mode):
    scratch = tempfile.mkdtemp(prefix="gp_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=40, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    if mode != "none":
        ground = kb.Cube(name="ground", scale=(HALF, HALF, 0.1), position=(0, 0, -0.1),
                         static=True, segmentation_id=1)
        ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
        scene += ground
        if mode == "magenta":
            ground.material = kb.PrincipledBSDFMaterial(color=(1.0, 0.0, 1.0, 1.0),
                                                        roughness=0.9, metallic=0.0)
        else:
            mat, info = pb.pbr_material(kb, ASSET, CAT, uv_scale=UVS)
            pb.apply_bpy_material(renderer, ground, mat)

    pb.enable_hdri_file(renderer, ENV, strength=1.0, bg_strength=1.0)

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(0.0, 0.0, rest), segmentation_id=2)
    scene += obj

    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = (0.9, -3.4, CAM_H)
    cam.look_at((0.0, 0.0, CAM_H - 0.08))
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    return np.array(out["rgba"], copy=True)[0][..., :3]


imgs = {}
for mode in ("none", "normal", "magenta"):
    imgs[mode] = render(mode)
    cv2.imwrite(os.path.join(OUT, f"probe_{mode}.png"), imgs[mode][..., ::-1])
    say(f"rendered {mode}")

h, w = imgs["none"].shape[:2]
say("")
say("Magenta detection: count pixels that are strongly magenta (R high, G low, B high)")
for mode in ("none", "normal", "magenta"):
    im = imgs[mode].astype(np.float32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    mag = (r > 80) & (b > 80) & (g < r * 0.5) & (g < b * 0.5)
    lower = mag[int(h * 0.55):, :]
    say(f"  {mode:<8} magenta px whole={int(mag.sum()):>8}  lower half={int(lower.sum()):>8}"
        f"  ({100.0*lower.sum()/(w*h*0.45):5.2f}% of lower half)")

say("")
say("If 'magenta' shows ~0% in the lower half, our plane is NOT visible there and")
say("the lower half is entirely the panorama's own ground.")
say("")
say("Difference between no-plane and normal-plane, by image band:")
d = np.abs(imgs["none"].astype(np.int16) - imgs["normal"].astype(np.int16))
for y0, y1, lab in ((0, 200, "sky"), (200, 300, "near horizon"),
                    (300, 360, "just below horizon"), (360, 500, "mid ground"),
                    (500, 720, "bottom")):
    band = d[y0:y1]
    say(f"  {lab:<22} max={band.max():>4}  mean={band.mean():>7.2f}")
PYEOF
