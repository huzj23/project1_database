#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The REAL cause of the seam, and the fix that respects 铁律四.
#
# Growing the plane made the step WORSE (up to +94 luminance), which rules out
# "our plane is too small" as the main fault and points at brightness instead.
#
# The reason: we were adding our OWN DirectionalLight (intensity 2.6).  That light
# illuminates our synthetic plane but NOT the panorama, whose ground is baked into
# the HDRI at its own exposure.  So our ground is lit by one sun and the panorama's
# ground by another -- two grounds, two exposures, a visible seam.
#
# That added sun is also a direct violation of 铁律四 ("只听场景作者光照，不私自加
# 太阳光").
#
# The principled fix: let the HDRI light the scene as well as fill the background.
# Then our ground and the panorama's ground are lit by the SAME environment and
# their brightness agrees by construction.
#
# This renders each environment BOTH ways and measures the step, so the claim is
# backed by numbers rather than by the argument sounding right.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_outdoor5"
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
    print("G5", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
HALF, UVS = 60.0, 21.0

ENVS = [
    ("kloppenheim_02",     "street/resid",  "grass_ground",  "grass_textures"),
    ("german_town_street", "street/town",   "asphalt_01",    "asphalt_textures"),
    ("autumn_park",        "park",          "grass_ground",  "grass_textures"),
    ("ballawley_park",     "park 2",        "grass_ground",  "grass_textures"),
    ("orlando_stadium",    "stadium",       "running_track", "sport_textures"),
]


def build(env, asset, cat, with_sun, strength):
    scratch = tempfile.mkdtemp(prefix="g5_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=40, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(HALF, HALF, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
    scene += ground
    mat, info = pb.pbr_material(kb, asset, cat, uv_scale=UVS)
    pb.apply_bpy_material(renderer, ground, mat)

    pb.enable_hdri_file(renderer, env, strength=strength, bg_strength=1.0)
    if with_sun:
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

    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = (0.9, -3.4, 1.15)
    cam.look_at((0.0, 0.0, 1.05))
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    return np.array(out["rgba"], copy=True)[0][..., :3]


def step_across_horizon(img):
    h, w = img.shape[:2]
    col = img[:, int(w * 0.5) - 80:int(w * 0.5) + 80].mean(axis=1)
    lum = 0.114 * col[:, 0] + 0.587 * col[:, 1] + 0.299 * col[:, 2]
    g = np.abs(np.diff(lum))
    lo, hi = int(h * 0.30), int(h * 0.90)
    row = lo + int(np.argmax(g[lo:hi]))
    above = lum[max(0, row - 12):row].mean()
    below = lum[row + 2:row + 14].mean()
    ours = lum[int(h * 0.80):int(h * 0.95)].mean()
    return row, above, below, below - above, ours


say(f"plane {2*HALF:.0f} m; comparing an added sun vs HDRI-only lighting")
say(f"{'env':<20}{'mode':<12}{'edge row':>9}{'above':>8}{'below':>8}{'STEP':>8}{'our ground':>12}")
for env, label, asset, cat in ENVS:
    for mode, sun, st in (("sun added", True, 0.9), ("hdri only", False, 1.0)):
        img = build(env, asset, cat, sun, st)
        row, above, below, step, ours = step_across_horizon(img)
        tag = "sun" if sun else "hdri"
        cv2.imwrite(os.path.join(OUT, f"{env}__{tag}.png"), img[..., ::-1])
        say(f"{env:<20}{mode:<12}{row:>9}{above:>8.1f}{below:>8.1f}{step:>+8.1f}{ours:>12.1f}")

say("")
say("small |STEP| = the ground blends into the backdrop; large = visible seam")
PYEOF
