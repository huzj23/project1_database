#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# THE FIX: shadow-catcher ground, so there is only ONE ground in the picture.
#
# Established by measurement:
#   * the HDRI's lower half IS ground, with its horizon at ~0 deg elevation
#   * we are NOT wrongly replacing it -- the magenta probe showed our plane covers
#     99.4% of the lower half, so the panorama's ground is already hidden
#   * plane SIZE is irrelevant (step stayed +44..+52 from 14 m to 800 m)
#   * yet a mismatch remains, because an equirectangular HDRI is a 2D image at
#     INFINITY: its ground carries the perspective of wherever it was shot and has
#     no parallax.  A real 3D plane lit by our camera can never line up with it.
#
# So stop trying to match two grounds. Keep ONE: the panorama's.
#
# The actor still needs something to rest on and cast a shadow onto, so the plane
# stays -- but as a SHADOW CATCHER.  Cycles renders it invisible to the camera
# while still receiving the shadow, so the ground the viewer sees is the HDRI's
# own, and the object's contact shadow lands on it correctly.
#
# Measured here: is the plane now invisible (no seam), and is the shadow present?
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_outdoor6"
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
    print("G6", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
HALF, UVS = 60.0, 21.0

ENVS = [
    ("kloppenheim_02",     "street / residential", "grass_ground",  "grass_textures"),
    ("german_town_street", "street / town",        "asphalt_01",    "asphalt_textures"),
    ("autumn_park",        "nature / park",        "grass_ground",  "grass_textures"),
    ("ballawley_park",     "nature / park 2",      "grass_ground",  "grass_textures"),
    ("orlando_stadium",    "sports / stadium",     "running_track", "sport_textures"),
]


def render(env, asset, cat, shadow_catcher):
    scratch = tempfile.mkdtemp(prefix="g6_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(HALF, HALF, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
    scene += ground
    mat, info = pb.pbr_material(kb, asset, cat, uv_scale=UVS)
    pb.apply_bpy_material(renderer, ground, mat)

    # HDRI lights the scene AND fills the background; no added sun (铁律四)
    pb.enable_hdri_file(renderer, env, strength=1.0, bg_strength=1.0)

    if shadow_catcher:
        go = ground.linked_objects[renderer]
        go.is_shadow_catcher = True

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(0.0, 0.0, rest), segmentation_id=2)
    scene += obj

    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = (0.9, -3.4, 1.15)
    cam.look_at((0.0, 0.0, 1.07))
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    return np.array(out["rgba"], copy=True)[0][..., :3]


def horizon_row(img):
    h, w = img.shape[:2]
    col = img[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
    lum = 0.114 * col[:, 0] + 0.587 * col[:, 1] + 0.299 * col[:, 2]
    sm = np.convolve(lum, np.ones(9) / 9, mode="same")
    g = np.abs(np.diff(sm))
    lo, hi = int(h * 0.25), int(h * 0.75)
    return lo + int(np.argmax(g[lo:hi]))


say(f"{'env':<20}{'mode':<16}{'horizon':>8}{'just below':>12}{'bottom':>9}{'DIFF':>8}")
for env, label, asset, cat in ENVS:
    for mode, sc in (("visible ground", False), ("shadow catcher", True)):
        img = render(env, asset, cat, sc)
        tag = "catch" if sc else "vis"
        cv2.imwrite(os.path.join(OUT, f"{env}__{tag}.png"), img[..., ::-1])
        hrow = horizon_row(img)
        h, w = img.shape[:2]
        col = img[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
        lum = 0.114 * col[:, 0] + 0.587 * col[:, 1] + 0.299 * col[:, 2]
        jb = lum[hrow + 6:hrow + 26].mean()
        bt = lum[int(h * 0.82):int(h * 0.96)].mean()
        say(f"{env:<20}{mode:<16}{hrow:>8}{jb:>12.1f}{bt:>9.1f}{jb - bt:>+8.1f}")

say("")
say("A shadow catcher should give DIFF near 0: one continuous ground (the")
say("panorama's), with the actor's contact shadow painted onto it.")
PYEOF
