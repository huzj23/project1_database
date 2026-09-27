#!/usr/bin/env bash
# T1 render progress monitor.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== stdout so far ==="
cat "$WS/tmp/t1_render_stdout.log" 2>/dev/null
echo
echo "=== rgb frame counts ==="
for d in "$REPO"/datasets/*/seed-*/x1; do
  [ -d "$d/rgb" ] || continue
  n=$(ls "$d/rgb" 2>/dev/null | wc -l)
  v=$(ls "$d"/*.mp4 2>/dev/null | head -1)
  echo "  $(basename $(dirname $(dirname $d)))/$(basename $d): rgb=$n video=${v:-none}"
done
echo
echo "=== current frame being rendered ==="
tail -3 "$WS/tmp/t1_render.log" 2>/dev/null
