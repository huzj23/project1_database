#!/usr/bin/env bash
# Verify the T3 final render actually started and is progressing.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== t3final session ==="
tmux ls 2>/dev/null | grep -E '^t3final' | sed 's/^/  /'

echo
echo "=== runner stdout ==="
cat "$WS/tmp/t3_final_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'

echo
echo "=== running process ==="
pgrep -af "generate.py" | sed 's/^/  /'

echo
echo "=== render log tail ==="
tail -6 "$WS/tmp/t3_final.log" 2>/dev/null | cut -c1-170 | sed 's/^/  /'

echo
echo "=== staged frames ==="
for c in "$REPO"/cache/turntable_*/seed-*/x1/images; do
  [ -d "$c" ] || continue
  echo "  $(echo $c | sed "s|$REPO/cache/||"): $(ls $c 2>/dev/null | wc -l)"
done
