#!/usr/bin/env bash
# Inspect the trajectory structure and export a contact-sheet of key frames so the
# clip can be reviewed locally.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-001001/x1"

echo "=== trajectory.json structure ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1"
raw = json.load(open(d + "/trajectory.json"))
print("  top-level type:", type(raw).__name__)
if isinstance(raw, dict):
    print("  keys:", list(raw.keys()))
    tr = raw.get("trajectory", raw)
else:
    tr = raw
print("  entries:", len(tr))
print("  first entry type:", type(tr[0]).__name__)
print("  first entry:", json.dumps(tr[0])[:300] if isinstance(tr[0], dict) else tr[0])
import numpy as np
p = np.array([s["position"] for s in tr])
print(f"  start={np.round(p[0],4).tolist()}")
print(f"  end  ={np.round(p[-1],4).tolist()}")
print(f"  x span={p[:,0].ptp():.4f} y span={p[:,1].ptp():.4f} z span={p[:,2].ptp():.4f}")
print(f"  z min={p[:,2].min():.5f} max={p[:,2].max():.5f}")
PY

echo
echo "=== build a contact sheet of 8 key frames ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/rgb"
fs = sorted(glob.glob(d + "/*.png"))
idx = [0, 10, 20, 30, 40, 50, 60, 80]
ims = [Image.open(fs[i]).convert("RGB").resize((640, 360)) for i in idx]
sheet = Image.new("RGB", (640*4, 360*2))
for k, im in enumerate(ims):
    sheet.paste(im, ((k % 4)*640, (k//4)*360))
out = "/data/raw/huzijian/project1_database/outcomes/_t1/ROLLING_CONTACT.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
sheet.save(out)
print("  wrote", out, "frames", idx)
PY
ls -la "$WS/outcomes/_t1/" 2>/dev/null | sed 's/^/  /'
