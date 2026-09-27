#!/usr/bin/env bash
# Monitor the red-wood turntable renders.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== ttwood runner ==="
cat "$WS/tmp/ttwood_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "=== running ==="
pgrep -af 'scripts/generate.py' | grep -v 'bash -c' | head -2 | sed 's/^/  /'
echo "=== staged frames ==="
for c in "$REPO"/cache/turntable_*/seed-*/x1/images; do
  [ -d "$c" ] || continue
  n=$(ls "$c" 2>/dev/null | wc -l)
  echo "  $(echo $c | sed "s|$REPO/cache/||"): $n"
done
echo "=== completed datasets ==="
for d in "$REPO"/datasets/turntable_*/seed-*/x1; do
  [ -d "$d" ] || continue
  echo "  $(echo $d | sed "s|$REPO/datasets/||") rgb=$(ls $d/rgb 2>/dev/null | wc -l) mp4=$([ -f $d/video.mp4 ] && echo yes || echo no)"
done
echo "=== render log tail ==="
tail -4 "$WS/tmp/tt_wood_render.log" 2>/dev/null | cut -c1-190 | sed 's/^/  /'
echo "=== load ==="
cut -d' ' -f1-3 /proc/loadavg | sed 's/^/  /'
