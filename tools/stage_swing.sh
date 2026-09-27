#!/usr/bin/env bash
# Stage the seed-1000 / random-policy sample for review.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x0.5"
OUT="$WS/outcomes/_P1_swing"
rm -rf "$OUT"; mkdir -p "$OUT"

for f in video.mp4 metadata.json trajectory.json collisions.json config.yaml; do
  [ -f "$D/$f" ] && cp -f "$D/$f" "$OUT/"
done

"$PY" - "$D" "$OUT" <<'PY'
import json, os, shutil, sys
import numpy as np
D, OUT = sys.argv[1], sys.argv[2]
md = json.load(open(os.path.join(D, "metadata.json")))
print(f"  camera   : {[round(v, 2) for v in (md.get('camera') or {}).get('position', [])]}")
print(f"  look_at  : {[round(v, 2) for v in (md.get('camera') or {}).get('look_at', [])]}")
print(f"  valid    : {(md.get('validation') or {}).get('valid')}")
frames = sorted(f for f in os.listdir(os.path.join(D, "rgb")) if f.endswith(".png"))
n = len(frames)
for k, i in enumerate(sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))):
    shutil.copy2(os.path.join(D, "rgb", frames[i]), os.path.join(OUT, f"f{k}.png"))
print(f"  staged {len(frames)} frames, picks at {[frames[i] for i in sorted(set([0, n//4, n//2, (3*n)//4, n-1]))]}")
PY
echo "  total: $(du -sh "$OUT" | cut -f1)"
