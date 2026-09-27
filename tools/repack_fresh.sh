#!/usr/bin/env bash
# Re-package the newest sample and report its real shape, so a stale copy cannot
# be mistaken for a fresh render.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x0.5"
OUT="$WS/outcomes/_P1_smoke"

echo "=== source ==="
echo "  dir        : $D"
echo "  rgb frames : $(ls "$D/rgb" 2>/dev/null | wc -l)"
echo "  newest rgb : $(ls -t "$D/rgb" 2>/dev/null | head -1)"
echo "  mtime      : $(stat -c %y "$D/metadata.json" 2>/dev/null)"
echo "  frame_count: $(grep -m1 'frame_count' "$D/config.yaml" 2>/dev/null)"
echo "  resolution : $(grep -m1 'resolution' "$D/config.yaml" 2>/dev/null)"

rm -rf "$OUT"; mkdir -p "$OUT"
cp -f "$D/video.mp4" "$D/trajectory.json" "$D/collisions.json" \
      "$D/metadata.json" "$D/config.yaml" "$OUT/" 2>/dev/null

"$WS/tools/conda_env/bin/python" - "$D" "$OUT" <<'PY'
import json, os, shutil, sys
import numpy as np
D, OUT = sys.argv[1], sys.argv[2]
frames = sorted(f for f in os.listdir(os.path.join(D, "rgb")) if f.endswith(".png"))
n = len(frames)
picks = sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))
for k, i in enumerate(picks):
    shutil.copy2(os.path.join(D, "rgb", frames[i]), os.path.join(OUT, f"f{k}_{frames[i]}"))
print(f"  copied {n}-frame set: " + ", ".join(frames[i] for i in picks))
PY

echo
echo "=== packaged ==="
ls "$OUT" | sed 's/^/  /'
