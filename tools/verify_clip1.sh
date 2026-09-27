#!/usr/bin/env bash
# Fetch clip 1 and verify it independently: frames distinct, video decodes,
# object actually moves, and the lighting is the authored one.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-001001/x1"

echo "=== video probe ==="
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,r_frame_rate,duration \
  -of default=noprint_wrappers=1 "$D/video.mp4" 2>&1 | sed 's/^/  /'

echo
echo "=== frame uniqueness (all 81) ==="
u=$(md5sum "$D/rgb"/*.png 2>/dev/null | awk '{print $1}' | sort -u | wc -l)
n=$(ls "$D/rgb"/*.png 2>/dev/null | wc -l)
echo "  $u unique of $n"

echo
echo "=== per-frame motion (pixels changed vs previous) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/rgb"
fs = sorted(glob.glob(os.path.join(d, "*.png")))
prev = None
big = 0
for i, f in enumerate(fs):
    a = np.asarray(Image.open(f).convert("RGB"), dtype=np.int16)
    if prev is not None:
        d2 = np.abs(a - prev)
        ch = int((d2.max(axis=2) > 2).sum())
        if ch > 500: big += 1
        if i < 4 or i % 20 == 0:
            print(f"  f{i:03d}: pixels_changed={ch:7d} mean={a.mean():.2f}")
    prev = a
print(f"  adjacent pairs with >500 changed pixels: {big}/{len(fs)-1}")
PY

echo
echo "=== trajectory: did the object actually move? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json
import numpy as np
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1"
tr = json.load(open(d + "/trajectory.json"))["trajectory"]
p = np.array([s["position"] for s in tr])
print(f"  frames={len(tr)}")
print(f"  start={np.round(p[0],4).tolist()}")
print(f"  end  ={np.round(p[-1],4).tolist()}")
print(f"  x span={p[:,0].ptp():.4f}  y span={p[:,1].ptp():.4f}  z span={p[:,2].ptp():.4f}")
print(f"  z min={p[:,2].min():.5f} max={p[:,2].max():.5f}")
PY

echo
echo "=== depth range ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/depth"
fs = sorted(glob.glob(d + "/*.png"))[:3]
for f in fs:
    a = np.asarray(Image.open(f))
    print(f"  {f.split('/')[-1]}: shape={a.shape} dtype={a.dtype} min={a.min()} max={a.max()} unique={len(np.unique(a))}")
PY
