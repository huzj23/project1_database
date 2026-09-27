#!/usr/bin/env bash
# Two problems to triage at once:
#  1. the T3 render: clips 5001 and 5002 are done, but no generate.py is running
#     and #6 has not started -- did the tmux session die?
#  2. what did the rolling subagent leave behind (it failed with no closing msg)?
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== t3final session ==="
tmux ls 2>/dev/null | grep -E '^t3final' | sed 's/^/  /' || echo "  t3final GONE"

echo
echo "=== t3 runner stdout (full) ==="
cat "$WS/tmp/t3_final_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'

echo
echo "=== t3 render log: last lines + error scan ==="
tail -8 "$WS/tmp/t3_final.log" 2>/dev/null | cut -c1-200 | sed 's/^/  /'
echo "  tracebacks: $(grep -c Traceback "$WS/tmp/t3_final.log" 2>/dev/null)"
grep -E 'Error|error:|Traceback|raise ' "$WS/tmp/t3_final.log" 2>/dev/null | tail -5 | cut -c1-200 | sed 's/^/  /'

echo
echo "=== any python/blender still alive? ==="
pgrep -af "generate.py" | sed 's/^/  /' || echo "  none"
pgrep -af "blender" | head -3 | sed 's/^/  /' || echo "  no blender"

echo
echo "=== datasets present ==="
for d in "$REPO"/datasets/turntable_*/seed-*/x1; do
  [ -d "$d" ] || continue
  echo "  $(echo $d | sed "s|$REPO/datasets/||") rgb=$(ls $d/rgb 2>/dev/null | wc -l) mp4=$([ -f $d/video.mp4 ] && echo yes || echo no)"
done

echo
echo "=== ROLLING subagent: what changed? ==="
echo "  --- rolling_gso.yaml camera + physics ---"
sed -n '/^camera:/,/^output:/p' "$REPO/configs/scenarios/rolling_gso.yaml" 2>/dev/null | sed 's/^/    /'
echo "  --- rolling.py orientation handling ---"
grep -n 'orientation\|quaternion\|side\|roll' "$REPO/src/physim/scenarios/rolling.py" 2>/dev/null | sed 's/^/    /'

echo
echo "=== recent file changes (last 3h) in repo ==="
find "$REPO/src" "$REPO/configs" "$REPO/assets" -newermt '-3 hours' -type f 2>/dev/null | grep -v __pycache__ | sed 's/^/  /'

echo
echo "=== rolling outcomes / new datasets ==="
ls -la "$WS/outcomes/_t1b" 2>/dev/null | sed 's/^/  /' || echo "  no _t1b dir"
ls -d "$REPO"/datasets/rolling/seed-* 2>/dev/null | sed 's/^/  /'
