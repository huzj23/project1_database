#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Where exactly IS the seam?
#
# The magenta probe proved our plane is visible and covers the lower half, so the
# seam is not "two grounds showing".  The step I kept measuring must therefore be
# the ground's OWN brightness gradient -- dark far away, brighter close up -- or a
# boundary between our plane and the backdrop somewhere specific.
#
# To tell those apart, find the seam's exact ROW and then ask what is on each side:
#   * if the row is where our plane's far edge is, it is a plane/backdrop boundary
#   * if the row is a smooth gradient, there is no boundary at all and what looked
#     like a seam is the panorama's own ground brightness ramp
#
# This renders with the ground DUPLICATED as a magenta slab whose top face sits at
# the same height, so the plane's exact silhouette can be read off the image.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_seam_locate"
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
    print("SL", *a, flush=True)

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
ENV = "german_town_street"
CAM_H, HALF, UVS = 1.15, 60.0, 21.0
FL = 35.0
SENSOR_W, SENSOR_H = 36.0, 36.0 / (16.0 / 9.0)


def render(with_ground):
    scratch = tempfile.mkdtemp(prefix="sl_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=40, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)
    if with_ground:
        ground = kb.Cube(name="ground", scale=(HALF, HALF, 0.1), position=(0, 0, -0.1),
                         static=True, segmentation_id=1)
        ground.material = kb.PrincipledBSDFMaterial(color=(1, 1, 1, 1), roughness=0.92)
        scene += ground
        mat, info = pb.pbr_material(kb, "asphalt_01", "asphalt_textures", uv_scale=UVS)
        pb.apply_bpy_material(renderer, ground, mat)
    pb.enable_hdri_file(renderer, ENV, strength=1.0, bg_strength=1.0)
    cam = kb.PerspectiveCamera(focal_length=FL, sensor_width=SENSOR_W)
    cam.position = (0.9, -3.4, CAM_H)
    cam.look_at((0.0, 0.0, CAM_H - 0.08))
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    return np.array(out["rgba"], copy=True)[0][..., :3]


g = render(True)
n = render(False)
cv2.imwrite(os.path.join(OUT, "with_ground.png"), g[..., ::-1])
cv2.imwrite(os.path.join(OUT, "no_ground.png"), n[..., ::-1])

h, w = g.shape[:2]
say(f"image {w}x{h}, camera h={CAM_H} m, plane half={HALF} m")
# predicted plane far-edge row, using the actual pinhole geometry
# camera pitches down slightly; compute the angle of the far edge below the axis
pitch = math.atan2(CAM_H - (CAM_H - 0.08), 3.4)          # look_at drop over distance
pitch_deg = math.degrees(math.atan2(-0.08, 3.4))
vfov = 2 * math.degrees(math.atan(SENSOR_H / (2 * FL)))
edge_deg = math.degrees(math.atan(CAM_H / HALF))
row_edge = h * 0.5 + (pitch_deg + edge_deg) / vfov * h
say(f"vertical FOV = {vfov:.2f} deg; camera pitch = {pitch_deg:+.2f} deg")
say(f"plane far edge is {edge_deg:.2f} deg below horizon -> predicted row {row_edge:.0f}")

# measure luminance profile down the centre
col = g[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
lum = 0.114 * col[:, 0] + 0.587 * col[:, 1] + 0.299 * col[:, 2]
cn = n[:, int(w * 0.5) - 100:int(w * 0.5) + 100].mean(axis=1)
lumn = 0.114 * cn[:, 0] + 0.587 * cn[:, 1] + 0.299 * cn[:, 2]

say("")
say("row : our-ground lum | backdrop-only lum | difference   <- big diff = plane edge")
for row in range(240, h, 20):
    d = lum[row] - lumn[row]
    mark = ""
    if abs(row - row_edge) < 12:
        mark = "  <-- predicted plane edge"
    say(f"{row:4d} : {lum[row]:14.1f} | {lumn[row]:17.1f} | {d:+10.1f}{mark}")

# the sharpest change in the WITH-GROUND image
grad = np.abs(np.diff(lum))
lo, hi = int(h * 0.30), int(h * 0.90)
peak = lo + int(np.argmax(grad[lo:hi]))
say("")
say(f"sharpest luminance change in with-ground image: row {peak} (grad {grad[peak]:.2f})")
say(f"predicted plane edge row: {row_edge:.0f}  -> match={abs(peak-row_edge)<15}")
say(f"is the profile smooth there? neighbours: "
    f"{lum[peak-25]:.1f} -> {lum[peak]:.1f} -> {lum[peak+25]:.1f}")
PYEOF
