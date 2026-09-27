#!/usr/bin/env bash
# Export review artefacts for the FIRST completed clip so the user can see the
# effect without waiting for all 14.
#
# Produces, under outcomes/_t1/:
#   ROLLING_clip.mp4        the real 81-frame video
#   ROLLING_CONTACT.png     8 key frames as a contact sheet
#   ROLLING_MOTION.png      a strip showing the object tracked across the frame
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-001001/x1"
OUT="$WS/outcomes/_t1"
mkdir -p "$OUT"

echo "=== copy the video ==="
cp "$D/video.mp4" "$OUT/ROLLING_clip.mp4"
ls -la "$OUT/ROLLING_clip.mp4" | sed 's/^/  /'

echo
echo "=== contact sheet: 8 key frames, full resolution halves ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/rgb"
out = "/data/raw/huzijian/project1_database/outcomes/_t1"
fs = sorted(glob.glob(d + "/*.png"))
idx = [0, 10, 20, 30, 40, 50, 60, 80]
w, h = 640, 360
sheet = Image.new("RGB", (w*4, h*2), (20, 20, 20))
for k, i in enumerate(idx):
    sheet.paste(Image.open(fs[i]).convert("RGB").resize((w, h)), ((k % 4)*w, (k//4)*h))
p = os.path.join(out, "ROLLING_CONTACT.png")
sheet.save(p)
print("  wrote", p, "frames", idx)
PY

echo
echo "=== motion strip: tight crops around the tracked object ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
import numpy as np
from PIL import Image
base = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/rgb"
out = "/data/raw/huzijian/project1_database/outcomes/_t1"
fs = sorted(glob.glob(base + "/*.png"))
stack = np.stack([np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in fs[::8]])
bg = np.median(stack, axis=0)
crops = []
for i in range(0, 81, 10):
    a = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
    diff = np.abs(a - bg).max(axis=2)
    m = diff > 25
    if m.sum() < 50:
        continue
    ys, xs = np.nonzero(m)
    cy, cx = int(ys.mean()), int(xs.mean())
    r = 130
    y0, y1 = max(0, cy-r), min(1080, cy+r)
    x0, x1 = max(0, cx-r), min(1920, cx+r)
    crops.append((i, Image.open(fs[i]).convert("RGB").crop((x0, y0, x1, y1)).resize((260, 260))))
if crops:
    strip = Image.new("RGB", (260*len(crops), 260), (20, 20, 20))
    for k, (i, im) in enumerate(crops):
        strip.paste(im, (k*260, 0))
    p = os.path.join(out, "ROLLING_MOTION.png")
    strip.save(p)
    print("  wrote", p, "frames", [i for i, _ in crops])
PY
ls -la "$OUT" | sed 's/^/  /'
