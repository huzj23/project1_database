#!/usr/bin/env bash
# Detailed T1 state: is the first sample finished and written out?
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== alive? ==="
pgrep -af "generate.py" | head -2

echo
echo "=== log tail ==="
tail -12 "$WS/tmp/t1_render.log" 2>/dev/null | cut -c1-200

echo
echo "=== rolling sample dir ==="
find "$REPO/datasets/rolling" -maxdepth 3 -type d 2>/dev/null | sed 's/^/  /'
for sub in rgb depth segmentation; do
  n=$(ls "$REPO/datasets/rolling/seed-1001/x1/$sub" 2>/dev/null | wc -l)
  echo "  $sub: $n"
done
ls -la "$REPO/datasets/rolling/seed-1001/x1/"*.mp4 "$REPO/datasets/rolling/seed-1001/x1/"*.json 2>/dev/null | sed 's/^/  /'

echo
echo "=== all datasets present ==="
ls "$REPO/datasets" 2>/dev/null | sed 's/^/  /'
