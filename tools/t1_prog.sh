#!/usr/bin/env bash
# Precise T1 progress: staged frames vs 81, and elapsed time.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== staged frames per sample ==="
for c in "$REPO"/cache/*/seed-*/x1/images; do
  [ -d "$c" ] || continue
  echo "  $c: $(ls $c 2>/dev/null | wc -l) frames"
done

echo
echo "=== completed samples ==="
for d in "$REPO"/datasets/*/seed-*/x1; do
  [ -d "$d" ] || continue
  n=$(ls "$d/rgb" 2>/dev/null | wc -l)
  v=$(ls "$d"/*.mp4 2>/dev/null | head -1)
  [ "$n" -gt 0 ] && echo "  $d: rgb=$n video=${v:-none}"
done

echo
echo "=== runner stdout ==="
cat "$WS/tmp/t1_render_stdout.log" 2>/dev/null | tr -d '\r'

echo
echo "=== process elapsed ==="
ps -o pid=,etime=,cmd= -p $(pgrep -f generate.py | head -1) 2>/dev/null

echo
echo "=== cache file mtime (newest) ==="
newest=$(ls -t "$REPO"/cache/*/seed-*/x1/images/*.png 2>/dev/null | head -1)
[ -n "$newest" ] && echo "  $newest  ($(date -r "$newest" '+%H:%M:%S'), now $(date '+%H:%M:%S'))"
