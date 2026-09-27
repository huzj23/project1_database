#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Decisive test: with the LIGHTING HELD FIXED, does plane size remove the seam?
#
# The previous run changed two things at once (size AND lighting), so it could not
# say which mattered.  This varies ONE thing.
#
# Lighting is HDRI-only (no added sun), which is both the fix for 铁律四 and the
# reason the two grounds are lit by the same environment.
#
# The test for a seam: compare the ground colour immediately below the horizon with
# the ground colour near the bottom of frame.  If our plane covers everything, both
# samples are OUR ground and they agree.  If a band of the panorama's own ground is
# showing, the sample just below the horizon is the PANORAMA's ground and the two
# disagree -- that disagreement IS the seam.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_ground_size"
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
    print("GZ", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
ENV, ASSET, CAT = "german_town_street", "asphalt_01", "asphalt_textures"
CAM_H = 1.15

# (half_extent, uv) -- uv scaled with size so texture DENSITY stays constant
SIZES = [(7.0, 2.5), (60.0, 21.0), (400.0, 140.0)]


def render(half, uvs):
    scratch = tempfile.mkdtemp(prefix="gz_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=40, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(half, half, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
    scene += ground
    mat, info = pb.pbr_material(kb, ASSET, CAT, uv_scale=uvs)
    pb.apply_bpy_material(renderer, ground, mat)

    # HDRI lights the scene AND fills the background -- no added sun (铁律四)
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


def find_horizon(img):
    """The horizon is the sharpest sustained vertical change in the upper half."""
    h, w = img.shape[:2]
    col = img[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
    lum = 0.114 * col[:, 0] + 0.587 * col[:, 1] + 0.299 * col[:, 2]
    k = 9
    sm = np.convolve(lum, np.ones(k) / k, mode="same")
    g = np.abs(np.diff(sm))
    lo, hi = int(h * 0.25), int(h * 0.75)
    return lo + int(np.argmax(g[lo:hi])), lum


say(f"{ENV}, HDRI-only lighting, plane size varied (one variable at a time)")
say(f"{'plane':>8}{'edge_deg':>10}{'horizon_row':>12}{'just below':>12}{'bottom':>9}{'DIFF':>8}{'verdict':>16}")
for half, uvs in SIZES:
    img = render(half, uvs)
    cv2.imwrite(os.path.join(OUT, f"half{int(half):03d}.png"), img[..., ::-1])
    hrow, lum = find_horizon(img)
    h = img.shape[0]
    just_below = lum[hrow + 6:hrow + 26].mean()
    bottom = lum[int(h * 0.82):int(h * 0.96)].mean()
    diff = just_below - bottom
    edge_deg = math.degrees(math.atan(CAM_H / half))
    verdict = "continuous" if abs(diff) < 12 else ("seam visible" if abs(diff) < 40 else "STRONG seam")
    say(f"{2*half:7.0f}m{edge_deg:9.2f}d{hrow:>12}{just_below:>12.1f}{bottom:>9.1f}"
        f"{diff:>+8.1f}{verdict:>16}")

say("")
say("just-below-horizon vs bottom: if our plane covers everything below the")
say("horizon both samples are OUR ground and agree; a gap means the panorama's")
say("own ground is still showing between them.")
PYEOF
