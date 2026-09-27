#!/usr/bin/env bash
# ===========================================================================
# Plan the two turntable fixes the user asked for.
#
# (1) "转盘应当只用之前冻结的红木纹理" -- the frozen choice is the Poly Haven
#     `dark_wood` PBR set (R/B 2.00, grain 49.8, chosen by measurement in V3.2).
#     Confirmed from the rendered pixels that the disc is currently plain GRAY
#     (R/B 0.99, saturation 2.2) because model.mtl is empty and the pipeline never
#     applies any material.  So the fix is to give the disc a material.
#     Check what material plumbing already exists inside the PIPELINE repo (as
#     opposed to code/scenarios/, which is outside it).
#
# (2) "镜头离物体有点太近了，拉远一点" -- the approved pose is
#     cam (0.934, -0.485, 1.1784) -> look (0.414, 0.175, 0.8084), focal 50 mm,
#     a distance of ~0.834 m.  Compute pull-back candidates that KEEP THE SAME
#     DIRECTION (so it stays the reviewed angle) at larger distance, and report
#     the resulting object size on screen.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== material plumbing inside the pipeline repo ==="
find src -name '*.py' | xargs grep -ln 'material' 2>/dev/null | sed 's/^/  /'
echo "  --- any pbr/backdrop helper vendored in? ---"
find . -maxdepth 3 -name '*backdrop*' -o -maxdepth 3 -name '*material*' 2>/dev/null | grep -v __pycache__ | sed 's/^/  /' || echo "  none"

echo
echo "=== the actor's own visual: does it carry a texture? ==="
find assets/objects/gso_sootheze_cold_therapy_elephant -type f | sed 's/^/  /'
echo "  --- its mtl ---"
cat assets/objects/gso_sootheze_cold_therapy_elephant/visual/*.mtl 2>/dev/null | head -12 | sed 's/^/  /'

echo
echo "=== camera pull-back geometry ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import math
import numpy as np
TOP = np.array([0.4140, 0.1750, 0.7584])
CAM = np.array([0.9340, -0.4850, 1.1784])
LOOK = np.array([0.4140, 0.1750, 0.8084])
d = CAM - LOOK
print(f"  approved: cam={CAM.tolist()} look={LOOK.tolist()}")
print(f"  offset from look = {np.round(d,4).tolist()}  distance = {np.linalg.norm(d):.4f} m")
# elephant size for reference
ELE = 0.267932   # largest extent, m
DISC_R = 0.30
print(f"  actor (elephant) largest extent = {ELE:.4f} m, disc radius = {DISC_R:.3f} m")
print()
print(f"  {'scale':>6} {'distance':>9} {'cam position':38s} {'actor frac':>10} {'disc frac':>10}")
for k in (1.0, 1.25, 1.5, 1.75, 2.0):
    cam = LOOK + d * k
    dist = np.linalg.norm(cam - LOOK)
    # focal 50, sensor 36 -> horizontal half-angle
    fov_h = 2 * math.atan(36.0 / (2 * 50.0))
    frame_w = 2 * dist * math.tan(fov_h / 2)
    print(f"  {k:6.2f} {dist:9.4f} ({cam[0]:7.4f},{cam[1]:7.4f},{cam[2]:7.4f})   "
          f"{ELE/frame_w:10.3f} {2*DISC_R/frame_w:10.3f}")
print()
print("  (actor frac = elephant extent / frame width; the old clip was ~0.29,")
print("   the frame is currently dominated by the disc -> pull back to include the table)")
PY

echo
echo "=== how big is the disc on screen in the CURRENT render? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -12
import glob
import numpy as np
from PIL import Image
D = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
     "physics-video-sim-main/datasets/turntable_carry/seed-005001/x1")
s = np.asarray(Image.open(sorted(glob.glob(D + "/segmentation/*.png"))[40]))
if s.ndim == 3: s = s[..., 0]
for L in np.unique(s).tolist():
    m = (s == L)
    if m.sum() < 500: continue
    ys, xs = np.nonzero(m)
    print(f"  seg {L}: {100*m.mean():5.1f}% of frame  bbox x[{xs.min()},{xs.max()}] "
          f"y[{ys.min()},{ys.max()}]  width={xs.max()-xs.min()} px of 1920")
PY
