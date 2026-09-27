#!/usr/bin/env bash
# ===========================================================================
# The actor (elephant) has NO segmentation label of its own: all 81 frames of a
# turntable clip contain only labels {0,3}, yet build_scene assigns
# environment=1, simulated_object=2, support=3.  L3 measures R/B 0.99 = the grey
# DISC, so the elephant is folded into label 0 (background).
#
# Determine whether the actor is (a) not visible at all, or (b) visible but
# unlabelled.  Either way it is a real defect to report; the user's clips show a
# plush elephant, so (b) is likely.  Method: the disc is a flat cylinder whose top
# face is a known plane, so pixels ABOVE the disc's silhouette that differ from the
# environment must be the actor.  Cross-check by differencing frame 0 against a
# render with the actor's trajectory collapsed (it stays put), which isolates it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== build_scene: object creation + segmentation ids (lines 195-262) ==="
awk 'NR>=195 && NR<=262' src/physim/render/blender_backend.py | cat -n | sed 's/^/  /'

echo
echo "=== is the actor inside the disc's silhouette or sticking out above it? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -24
import glob, json
import numpy as np
from PIL import Image
D = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
     "physics-video-sim-main/datasets/turntable_spin/seed-005001/x1")
fs = sorted(glob.glob(D + "/rgb/*.png"))
ss = sorted(glob.glob(D + "/segmentation/*.png"))
# L3 = disc.  Look for pixels inside the L3 bounding box that are NOT L3 -> the actor.
for i in (0, 20, 40, 60, 80):
    img = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
    s = np.asarray(Image.open(ss[i]))
    if s.ndim == 3: s = s[..., 0]
    disc = (s == 3)
    ys, xs = np.nonzero(disc)
    y0,y1,x0,x1 = ys.min(), ys.max(), xs.min(), xs.max()
    box = np.zeros_like(disc); box[y0:y1+1, x0:x1+1] = True
    holes = box & ~disc
    print(f"  frame {i}: disc bbox {x1-x0}x{y1-y0}px, inside-box non-disc = {holes.sum()}px")
    if holes.sum() > 300:
        px = img[holes]
        r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        hy, hx = np.nonzero(holes)
        print(f"      -> that region: R={r:6.1f} G={g:6.1f} B={b:6.1f} R/B={r/max(b,1e-6):5.2f}"
              f"  y[{hy.min()},{hy.max()}] x[{hx.min()},{hx.max()}]")
        print(f"      disc pixels  : R={img[disc][:,0].mean():6.1f} "
              f"G={img[disc][:,1].mean():6.1f} B={img[disc][:,2].mean():6.1f}")
# how many distinct colours are on the disc top face? a plush elephant has its own
print()
print("  --- colour histogram inside the disc bbox (is a second object present?) ---")
img = np.asarray(Image.open(fs[0]).convert("RGB"), dtype=np.float32)
s = np.asarray(Image.open(ss[0]))
if s.ndim == 3: s = s[..., 0]
disc = (s == 3); ys, xs = np.nonzero(disc)
sub = img[ys.min():ys.max()+1, xs.min():xs.max()+1].reshape(-1,3)
grey = sub[(np.abs(sub[:,0]-sub[:,2]) < 6)]
col  = sub[(np.abs(sub[:,0]-sub[:,2]) >= 6)]
print(f"    near-neutral pixels (disc/grey): {len(grey):7d}  mean={grey.mean(0).round(1) if len(grey) else '-'}")
print(f"    chromatic pixels (something else): {len(col):7d}  mean={col.mean(0).round(1) if len(col) else '-'}")
PY
