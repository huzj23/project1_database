#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Does the HDRI provide its own ground, and where is its horizon?
#
# The user's question is the right one: the panorama is an equirectangular image,
# so its LOWER HALF is ground imagery.  We are not "wrongly replacing" it -- but
# we may be failing to line up with it.  This measures the facts:
#
#   * find the horizon row (strongest vertical change in the equirect image)
#   * convert that row to an elevation angle (row 0 = +90 deg, middle = 0 deg)
#   * sample the panorama's own ground colour just below the horizon
#
# If the horizon sits at 0 deg, then everything below it in the panorama is the
# panorama's ground -- and our synthetic plane has to MEET it at exactly 0 deg, or
# the viewer sees a seam: our ground, then the panorama's ground at a different
# scale and brightness, then sky.
# ---------------------------------------------------------------------------
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

"$PY" -u - "$WS" <<'PYEOF'
import sys, os, math
WS = sys.argv[1]
import numpy as np
import cv2

HDRI = os.path.join(WS, "models/hdri_hdr")
ENVS = ["kloppenheim_02", "german_town_street", "autumn_park",
        "ballawley_park", "orlando_stadium"]

print("HDRI   size        horizon_row  horizon_elev   ground_rgb(below)   sky_rgb(above)")
for e in ENVS:
    p = os.path.join(HDRI, f"{e}_4k.hdr")
    if not os.path.isfile(p):
        print(f"{e:<20} MISSING")
        continue
    img = cv2.imread(p, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
    if img is None:
        print(f"{e:<20} unreadable")
        continue
    h, w = img.shape[:2]
    # luminance per row, median across columns so trees/lamps do not dominate
    lum = np.median(img[..., :3], axis=(1, 2))
    # the horizon is the row with the steepest sustained drop going down
    k = max(3, h // 200)
    smooth = np.convolve(lum, np.ones(k) / k, mode="same")
    d = np.abs(np.gradient(smooth))
    lo, hi = int(h * 0.25), int(h * 0.85)      # horizon should be near the middle
    row = lo + int(np.argmax(d[lo:hi]))
    # equirect: row 0 is +90 deg (zenith), row h/2 is 0 deg (horizon)
    elev = (0.5 - row / float(h)) * 180.0
    below = img[min(h - 1, row + int(h * 0.03)):min(h, row + int(h * 0.10)), :, :3]
    above = img[max(0, row - int(h * 0.10)):max(1, row - int(h * 0.03)), :, :3]
    gb = below.reshape(-1, 3).mean(axis=0) if below.size else np.zeros(3)
    sa = above.reshape(-1, 3).mean(axis=0) if above.size else np.zeros(3)
    print(f"{e:<20} {w}x{h:<6} {row:>10}   {elev:+7.2f} deg   "
          f"({gb[2]:6.3f},{gb[1]:6.3f},{gb[0]:6.3f})   ({sa[2]:6.3f},{sa[1]:6.3f},{sa[0]:6.3f})")

print()
print("Interpretation:")
print("  horizon_elev near 0 deg  -> the panorama's own ground occupies everything")
print("                              below eye level, so a synthetic plane MUST")
print("                              cover it entirely or the two will both show.")
PYEOF
