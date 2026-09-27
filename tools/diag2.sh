#!/usr/bin/env bash
# ===========================================================================
# Diagnose two things.
#
# (a) Frame file naming: my mask lookup used 0001.png but the actual name differs.
# (b) `declared_materials` was {} in MY still harness while generate.py recorded the
#     full dark_wood block.  Either the disc material did not apply in my harness
#     (so my still is grey and NOT valid quality evidence), or diagnostics differ.
#     Measure the still's disc pixels to settle it.
# (c) The preview path re-runs sample+simulate and then FAILS validation
#     (disc_did_not_rotate) for the turntable, so blender_preview_scene.py cannot
#     build a turntable preview.  Confirm and note it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"
SAMPLE="datasets/turntable_spin/seed-005002/x1"

echo "=== (a) actual frame file names ==="
ls "$SAMPLE/rgb" | head -3 | sed 's/^/  rgb: /'
ls "$SAMPLE/segmentation" | head -3 | sed 's/^/  seg: /'
echo "  counts: rgb=$(ls $SAMPLE/rgb | wc -l) seg=$(ls $SAMPLE/segmentation | wc -l)"

echo
echo "=== (b) measure the STILL against a delivered frame ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -14
import glob, os
import numpy as np
from PIL import Image
OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"
SAMPLE = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
          "physics-video-sim-main/datasets/turntable_spin/seed-005002/x1")
segs = sorted(glob.glob(SAMPLE + "/segmentation/*.png"))
rgbs = sorted(glob.glob(SAMPLE + "/rgb/*.png"))
print(f"  seg files={len(segs)} first={os.path.basename(segs[0])}")
s = np.asarray(Image.open(segs[0]))
if s.ndim == 3: s = s[..., 0]
lab = [int(L) for L in np.unique(s) if L != 0]
L = max(lab, key=lambda l: (s == l).sum())
m = (s == L)
print(f"  disc label L{L} area={100*m.mean():.1f}%")

st = np.asarray(Image.open(f"{OUT}/STILL_turntable_spin_seed5002_final.png").convert("RGB"), dtype=np.float32)
px = st[m]
r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
print(f"  STILL disc  : R={r:6.1f} G={g:6.1f} B={b:6.1f}  R/B={r/max(b,1e-6):5.2f} R/G={r/max(g,1e-6):5.2f}")
for i in (0, 40, 80):
    c = np.asarray(Image.open(rgbs[i]).convert("RGB"), dtype=np.float32)[m]
    r2,g2,b2 = c[:,0].mean(), c[:,1].mean(), c[:,2].mean()
    print(f"  DELIVERED {i:3d}: R={r2:6.1f} G={g2:6.1f} B={b2:6.1f}  R/B={r2/max(b2,1e-6):5.2f} R/G={r2/max(g2,1e-6):5.2f}")
print("  dark_wood target R/B 1.99 ; grey would be R/B 0.99")
PY

echo
echo "=== (c) does the preview path support the turntable at all? ==="
grep -n 'def prepare_sample' -A 30 src/physim/pipeline.py | grep -nE 'simulate|validate|PyBullet|support' | head -10 | sed 's/^/  /'
echo "  --- try preview with a SINGLE-BODY scenario to see if the path works at all ---"
"$BLENDER" --background --factory-startup \
  --python scripts/blender_preview_scene.py -- \
  --config configs/server.yaml --scenario free_fall_gso --seed 3001 \
  --save-blend "$OUT/free_fall-seed-3001-preview.blend" \
  --sample-root datasets/free_fall/seed-003001/x1 2>&1 \
  | grep -aE 'PHYSIM_PREVIEW|Error|Traceback|RuntimeError' | tail -3 | cut -c1-300 | sed 's/^/  /'
echo "  free_fall blend: $([ -f "$OUT/free_fall-seed-3001-preview.blend" ] && echo OK || echo MISSING)"
