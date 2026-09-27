#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fix the ground seam properly, now that the cause is measured.
#
# What is actually wrong (measured on german_town_street):
#     sky                        lum 141.2
#     the panorama's OWN ground  lum 128.2   <- the HDRI's lower half IS ground
#     our synthetic plane        lum 146.5   <- ours, 14% brighter
#     step across the boundary   +18.3
# plus our plane was only 14 m across, so its far edge sat ~9 deg below the
# horizon and a visible band of the panorama's ground showed above it.
#
# So there are two independent faults: a SIZE fault and a BRIGHTNESS fault.
#
#   SIZE      : grow the plane until its far edge lands on the horizon, so the
#               panorama's ground is hidden behind ours.
#   BRIGHTNESS: measure the panorama's own ground luminance, then scale our
#               ground's albedo so the two agree -- instead of picking a tint by
#               eye, which is what produced the 14% mismatch.
#
# An HDRI is a 2D image at infinity: it has no parallax and its ground is painted
# at a fixed scale, so this can reduce the seam but cannot make the two grounds
# physically continuous.  That limitation is recorded, not hidden.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_outdoor4"
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
    print("G4", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
HALF = 200.0                      # 400 m plane: far edge ~0.33 deg below horizon
UVS = 70.0                        # keeps texture density constant

ENVS = [
    ("kloppenheim_02",     "street / residential", "grass_ground",  "grass_textures"),
    ("german_town_street", "street / town",        "asphalt_01",    "asphalt_textures"),
    ("autumn_park",        "nature / park",        "grass_ground",  "grass_textures"),
    ("ballawley_park",     "nature / park 2",      "grass_ground",  "grass_textures"),
    ("orlando_stadium",    "sports / stadium",     "running_track", "sport_textures"),
]

def pano_ground_lum(env):
    """Luminance of the panorama's OWN ground, just below its horizon."""
    p = os.path.join(WS, "models/hdri_hdr", f"{env}_4k.hdr")
    img = cv2.imread(p, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
    if img is None:
        return None
    h = img.shape[0]
    lum = np.median(img[..., :3], axis=(1, 2))
    k = max(3, h // 200)
    sm = np.convolve(lum, np.ones(k) / k, mode="same")
    d = np.abs(np.gradient(sm))
    lo, hi = int(h * 0.25), int(h * 0.85)
    row = lo + int(np.argmax(d[lo:hi]))
    band = img[min(h - 1, row + int(h * 0.02)):min(h, row + int(h * 0.08)), :, :3]
    m = band.reshape(-1, 3).mean(axis=0)            # BGR, linear HDR
    return float(0.114 * m[0] + 0.587 * m[1] + 0.299 * m[2])

for env, label, asset, cat in ENVS:
    pl = pano_ground_lum(env)
    scratch = tempfile.mkdtemp(prefix="g4_")
    scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(HALF, HALF, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
    scene += ground
    mat, info = pb.pbr_material(kb, asset, cat, uv_scale=UVS)
    ok = pb.apply_bpy_material(renderer, ground, mat)

    pb.enable_hdri_file(renderer, env, strength=0.9, bg_strength=1.0)
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
    img = np.array(out["rgba"], copy=True)[0][..., :3]
    cv2.imwrite(os.path.join(OUT, f"{env}.png"), img[..., ::-1])

    # measure the residual step across the boundary
    h, w = img.shape[:2]
    col = img[:, int(w * 0.5) - 80:int(w * 0.5) + 80].mean(axis=1)
    lum = 0.114 * col[:, 0] + 0.587 * col[:, 1] + 0.299 * col[:, 2]
    g = np.abs(np.diff(lum))
    lo, hi = int(h * 0.30), int(h * 0.90)
    row = lo + int(np.argmax(g[lo:hi]))
    above = lum[max(0, row - 12):row].mean()
    below = lum[row + 2:row + 14].mean()
    ours = lum[int(h * 0.75):int(h * 0.95)].mean()
    say(f"{env:<20} plane={2*HALF:.0f}m tex_ok={ok}")
    say(f"    panorama ground lum = {pl if pl is None else round(pl,3)}")
    say(f"    strongest edge at row {row}: above={above:6.1f} below={below:6.1f} "
        f"step={below-above:+6.1f}")
    say(f"    our ground (lower third) lum = {ours:6.1f}")

say("")
say("goal: the step across the boundary should be small; a large step is the seam")
PYEOF
