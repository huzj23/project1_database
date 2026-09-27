#!/usr/bin/env bash
# STATUS + RECON before the next round.
#  1. what T1 actually produced (the damping clips failed on a manifest gate)
#  2. what the turntable subagent produced, and what camera it used
#  3. the camera pose I previously got approved for the turntable-on-table render
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== T1 v2 stdout ==="
cat "$WS/tmp/t1_render2_stdout.log" 2>/dev/null | tr -d '\r'

echo
echo "=== every dataset sample ==="
for d in "$REPO"/datasets/*/seed-*/x1; do
  [ -d "$d" ] || continue
  n=$(ls "$d/rgb" 2>/dev/null | wc -l)
  v=$([ -f "$d/video.mp4" ] && echo yes || echo no)
  ok=$(grep -o '"valid": [a-z]*' "$d/metadata.json" 2>/dev/null | head -1)
  echo "  $(echo $d | sed "s|$REPO/datasets/||") rgb=$n video=$v $ok"
done

echo
echo "=== processes / sessions ==="
pgrep -af "generate.py" | head -3 | sed 's/^/  /'
tmux ls 2>/dev/null | grep -E 't1b|t3dev|t3gate' | sed 's/^/  /'

echo
echo "=== the turntable camera used by the subagent ==="
for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  echo "--- $f ---"
  sed -n '/^camera:/,/^output:/p' "$REPO/$f" 2>/dev/null | sed 's/^/    /'
done

echo
echo "=== previously-approved turntable camera (tt_on_table.sh) ==="
grep -n -iE 'camera|focal|look_at|azimuth|side|position' "$WS/tools/tt_on_table.sh" 2>/dev/null | head -40 | sed 's/^/  /'
