#!/usr/bin/env bash
# Verify consecutive rendered frames are actually DISTINCT.
#
# An earlier bug made every frame byte-identical (physics was never transcribed to
# keyframes).  The brightness figures for frames 1-3 looked suspiciously similar
# (mean 118.06 / 118.05 / 118.05), so check md5 and the pixel difference directly.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
C="$REPO/cache/rolling/seed-001001/x1/images"

echo "=== md5 of staged frames ==="
md5sum "$C"/*.png 2>/dev/null | awk '{print substr($1,1,12), $2}' | sed 's/^/  /'

echo
echo "=== unique count ==="
n=$(ls "$C"/*.png 2>/dev/null | wc -l)
u=$(md5sum "$C"/*.png 2>/dev/null | awk '{print $1}' | sort -u | wc -l)
echo "  $u unique of $n"

echo
echo "=== pairwise pixel differences ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
import numpy as np
from PIL import Image
fs = sorted(glob.glob("/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/cache/rolling/seed-001001/x1/images/*.png"))
ims = [np.asarray(Image.open(f).convert("RGB"), dtype=np.int16) for f in fs]
print(f"  {len(ims)} frames")
for i in range(len(ims)-1):
    d = np.abs(ims[i+1]-ims[i])
    print(f"  f{i+1:04d}->f{i+2:04d}: maxdiff={d.max():3d} pixels_changed={(d.max(axis=2)>2).sum():6d} "
          f"mean_abs={d.mean():.4f}")
PY
