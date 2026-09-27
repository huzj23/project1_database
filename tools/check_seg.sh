#!/usr/bin/env bash
# Why is subject_area always 0.00%?  Inspect the segmentation output directly.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== segmentation file stats for one seed ==="
D="$REPO/datasets/free_fall/seed-001003/x0.5"
ls -la "$D/segmentation" 2>/dev/null | head -5 | sed 's/^/  /'
echo "  frame count: $(ls "$D/segmentation" 2>/dev/null | wc -l)"

"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import os, sys
import numpy as np
import cv2
D = sys.argv[1]
seg = os.path.join(D, "segmentation")
files = sorted(f for f in os.listdir(seg) if f.endswith(".png"))
print(f"  files: {len(files)}")
for n in files[:3]:
    img = cv2.imread(os.path.join(seg, n), cv2.IMREAD_UNCHANGED)
    print(f"    {n}: shape={None if img is None else img.shape} "
          f"dtype={None if img is None else img.dtype} "
          f"min={None if img is None else img.min()} "
          f"max={None if img is None else img.max()} "
          f"unique={None if img is None else len(np.unique(img))}")
    if img is not None:
        u, c = np.unique(img, return_counts=True)
        top = sorted(zip(c, u), reverse=True)[:5]
        print(f"      top values (count,value): {top}")

print()
print("  --- rgb for comparison ---")
rgb = os.path.join(D, "rgb")
rf = sorted(f for f in os.listdir(rgb) if f.endswith(".png"))
im = cv2.imread(os.path.join(rgb, rf[0]))
print(f"    {rf[0]}: shape={im.shape} mean={im.mean():.1f} std={im.std():.1f}")
PY
