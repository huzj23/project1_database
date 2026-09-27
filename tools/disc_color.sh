#!/usr/bin/env bash
# ===========================================================================
# The disc has NO material: model.mtl is empty and the renderer applies none.
# Confirm that from the RENDERED PIXELS, then find where the frozen dark_wood
# PBR texture lives and how it is applied (pb.pbr_material / apply_bpy_material),
# so the same treatment can be applied inside the real pipeline.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== what colour is the disc in the rendered clip? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -25
import glob
import numpy as np
from PIL import Image
D = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
     "physics-video-sim-main/datasets/turntable_carry/seed-005001/x1")
fs = sorted(glob.glob(D + "/rgb/*.png"))
seg = sorted(glob.glob(D + "/segmentation/*.png"))
f = fs[40]
img = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
s = np.asarray(Image.open(seg[40]))
if s.ndim == 3: s = s[..., 0]
print(f"  frame {f.split('/')[-1]}  seg labels: {np.unique(s).tolist()}")
for L in np.unique(s).tolist():
    m = (s == L)
    if m.sum() < 500: continue
    px = img[m]
    r, g, b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
    print(f"    seg {L}: {m.sum():8d} px  R={r:6.1f} G={g:6.1f} B={b:6.1f}  "
          f"R/B={r/max(b,1e-6):.2f} R/G={r/max(g,1e-6):.2f}  "
          f"sat={px.max(axis=1).mean()-px.min(axis=1).mean():5.1f}")
print("  (frozen dark_wood measured R/B=1.83, R/G=1.58 on the finished render)")
PY

echo
echo "=== the pbr material helpers ==="
find "$WS/code" -name 'phyco_backdrops*' 2>/dev/null | sed 's/^/  /'
grep -n 'def pbr_material\|def apply_bpy_material' -A 25 \
  $(find "$WS/code" -name 'phyco_backdrops.py' | head -1) 2>/dev/null | head -60 | sed 's/^/  /'

echo
echo "=== does the pipeline have any material hook for the actor/support? ==="
grep -rn 'pbr_material\|apply_bpy_material\|phyco_backdrops' src/ scripts/ 2>/dev/null | sed 's/^/  /' || echo "  NONE - the pipeline never applies a PBR material"
