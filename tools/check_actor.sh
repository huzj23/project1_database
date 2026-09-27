#!/usr/bin/env bash
# ===========================================================================
# TWO things I must verify MYSELF about the new material hook.
#
# (1) DANGER: turntable.py sets `support_material=disc.material`.  If the renderer
#     ever applied that to the ACTOR, the elephant would come out wood-coloured.
#     The whole point is a red-wood DISC with a plush elephant on it.  So measure
#     the actor's pixels and confirm it is NOT wood.
#
# (2) The earlier segmentation readout for a turntable clip showed labels {0, 3}
#     only, even though build_scene assigns environment=1, actor=2, disc=3.  So
#     either the actor is unlabelled (a real defect worth reporting) or I
#     mis-identified which label is which.  Establish it concretely: the DISC is
#     the thing that rotates, and the ACTOR rides on it, so track each label's
#     radius from the disc axis.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== render progress ==="
cat "$WS/tmp/ttwood_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
pgrep -af 'scripts/generate.py' | grep -v 'bash -c' | head -1 | sed 's/^/  running: /'

echo
echo "=== segmentation labels + per-label colour, OLD (grey) turntable clip ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import glob
import numpy as np
from PIL import Image
D = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
     "physics-video-sim-main/datasets/turntable_spin/seed-005001/x1")
fs = sorted(glob.glob(D + "/rgb/*.png"))
ss = sorted(glob.glob(D + "/segmentation/*.png"))
print(f"  rgb={len(fs)} seg={len(ss)}")
for i in (0, 40, 80):
    img = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
    s = np.asarray(Image.open(ss[i]))
    if s.ndim == 3: s = s[..., 0]
    print(f"  --- frame {i} : labels {np.unique(s).tolist()} ---")
    for L in np.unique(s).tolist():
        m = (s == L)
        if m.sum() < 200: continue
        px = img[m]
        r, g, b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        ys, xs = np.nonzero(m)
        print(f"    L{L}: {m.sum():8d}px ({100*m.mean():5.1f}%) R={r:6.1f} G={g:6.1f} "
              f"B={b:6.1f} R/B={r/max(b,1e-6):5.2f} bbox x[{xs.min()},{xs.max()}] "
              f"y[{ys.min()},{ys.max()}]")
PY

echo
echo "=== does the actor appear as its own label anywhere? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -14
import glob, collections
import numpy as np
from PIL import Image
D = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
     "physics-video-sim-main/datasets/turntable_spin/seed-005001/x1")
seen = collections.Counter()
for p in sorted(glob.glob(D + "/segmentation/*.png")):
    s = np.asarray(Image.open(p))
    if s.ndim == 3: s = s[..., 0]
    for L in np.unique(s).tolist():
        seen[int(L)] += 1
print(f"  labels across all 81 frames (label: frames present) = {dict(seen)}")
print("  build_scene assigns: environment=1, simulated_object(actor)=2, support(disc)=3")
PY
