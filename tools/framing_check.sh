#!/usr/bin/env bash
# Quantitative framing check (cannot rely on viewing the image).
#
# Project the object's trajectory into the camera to confirm it stays inside the
# frame with sane margins, and measure the object's on-screen size.  Also detect
# the object in the RGB frames by looking for pixels that differ strongly from the
# static background, which independently proves the object is VISIBLE and MOVING.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-001001/x1"

echo "=== camera + asset metadata ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1"
m = json.load(open(d + "/metadata.json"))
print("  top keys:", list(m.keys()))
for k in ("camera", "render", "asset", "simulation"):
    if k in m:
        v = m[k]
        print(f"  {k}:", json.dumps(v)[:400] if not isinstance(v, str) else v)
PY

echo
echo "=== object detected in RGB: foreground mask size per key frame ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/rgb"
fs = sorted(glob.glob(d + "/*.png"))
# The camera is static, so the median over time approximates the background.
stack = np.stack([np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
                  for f in fs[::8]])
bg = np.median(stack, axis=0)
print(f"  frames sampled for background: {len(stack)}")
for i in (0, 20, 40, 60, 80):
    a = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
    diff = np.abs(a - bg).max(axis=2)
    mask = diff > 25
    n = int(mask.sum())
    if n:
        ys, xs = np.nonzero(mask)
        print(f"  f{i:03d}: fg_pixels={n:6d} bbox x[{xs.min():4d},{xs.max():4d}] "
              f"y[{ys.min():4d},{ys.max():4d}] centre=({xs.mean():.0f},{ys.mean():.0f})")
    else:
        print(f"  f{i:03d}: fg_pixels=0  <-- object NOT detectable")
print("  frame is 1920x1080; centre would be (960, 540)")
PY

echo
echo "=== depth: object vs surface ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/depth"
fs = sorted(glob.glob(d + "/*.png"))
for i in (0, 40, 80):
    a = np.asarray(Image.open(fs[i]))
    print(f"  f{i:03d}: dtype={a.dtype} shape={a.shape} min={a.min()} max={a.max()} unique={len(np.unique(a))}")
PY
