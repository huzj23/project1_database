#!/usr/bin/env bash
# T3 + rolling status.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== t3 runner stdout ==="
cat "$WS/tmp/t3_final_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "=== running ==="
pgrep -af generate.py | head -1 | sed 's/^/  /'
echo "=== turntable datasets ==="
for d in "$REPO"/datasets/turntable_*/seed-*/x1; do
  [ -d "$d" ] || continue
  echo "  $(echo $d | sed "s|$REPO/datasets/||") rgb=$(ls $d/rgb 2>/dev/null | wc -l) mp4=$([ -f $d/video.mp4 ] && echo yes || echo no)"
done
echo "=== cache staged ==="
for c in "$REPO"/cache/turntable_*/seed-*/x1/images; do
  [ -d "$c" ] || continue
  echo "  $(echo $c | sed "s|$REPO/cache/||"): $(ls $c 2>/dev/null | wc -l)"
done
