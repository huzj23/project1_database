#!/usr/bin/env bash
# Package seed-1000 for review, with camera diagnostics.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x0.5"
OUT="$WS/outcomes/_P1_smoke"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -f "$D/video.mp4" "$D/trajectory.json" "$D/collisions.json" \
      "$D/metadata.json" "$D/config.yaml" "$OUT/" 2>/dev/null

"$WS/tools/conda_env/bin/python" - "$D" "$OUT" <<'PY'
import json, os, shutil, sys
import numpy as np
D, OUT = sys.argv[1], sys.argv[2]
md = json.load(open(os.path.join(D, "metadata.json")))
cam = (md.get("camera") or {}).get("position")
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
lo, hi = c.min(axis=0), c.max(axis=0)

print(f"  camera        : {[round(v, 2) for v in cam]}")
print(f"  trajectory    : x[{lo[0]:.2f},{hi[0]:.2f}] y[{lo[1]:.2f},{hi[1]:.2f}] z[{lo[2]:.2f},{hi[2]:.2f}]")
ctr = (lo + hi) / 2
print(f"  stand-off     : {np.linalg.norm(np.array(cam) - ctr):.2f} m")
print(f"  look-at       : {[round(v, 2) for v in ((md.get('camera') or {}).get('look_at') or [])]}")
look = (md.get("camera") or {}).get("look_at")
if look:
    d = np.array(look) - np.array(cam)
    print(f"  view dir (xy) : ({d[0]:.2f}, {d[1]:.2f})  -> looking "
          f"{'toward +x' if d[0] > 0 else 'toward -x'}, "
          f"{'toward +y' if d[1] > 0 else 'toward -y'}")

frames = sorted(f for f in os.listdir(os.path.join(D, "rgb")) if f.endswith(".png"))
n = len(frames)
for k, i in enumerate([0, n // 4, n // 2, 3 * n // 4, n - 1]):
    shutil.copy2(os.path.join(D, "rgb", frames[i]), os.path.join(OUT, f"f{k}_{frames[i]}"))
print("  copied:", ", ".join(frames[i] for i in [0, n // 4, n // 2, 3 * n // 4, n - 1]))
PY

echo "  total: $(du -sh "$OUT" | cut -f1)"
