#!/usr/bin/env bash
# Decisive cleanup: kill every generate.py and the stale t1 session, verify, then
# relaunch the corrected runner under a NEW session name (t1b) so the old name
# cannot collide.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== before ==="
echo "  generate.py: $(pgrep -cf generate.py)"
tmux ls 2>/dev/null | grep -E '^t1' | sed 's/^/  /'

echo
echo "=== kill all render processes ==="
pkill -9 -f "generate.py" 2>/dev/null
sleep 2
# any stragglers
for pid in $(pgrep -f "generate.py"); do kill -9 "$pid" 2>/dev/null; done
sleep 1
echo "  generate.py now: $(pgrep -cf generate.py)"

echo
echo "=== kill t1 / t1b / t1probe sessions ==="
for s in t1 t1b t1probe; do
  tmux kill-session -t "$s" 2>/dev/null && echo "  killed $s" || echo "  $s absent"
done
sleep 1
echo "  remaining t1* sessions:"
tmux ls 2>/dev/null | grep -E '^t1' | sed 's/^/    /' || echo "    none"

echo
echo "=== relaunch as t1b ==="
tmux new-session -d -s t1b "bash $WS/tools/t1_render2.sh > $WS/tmp/t1_render2_stdout.log 2>&1"
sleep 6
tmux ls 2>/dev/null | grep -E '^t1b' | sed 's/^/  /'
pgrep -af "generate.py" | head -2 | sed 's/^/  /'
echo "  --- stdout ---"
cat "$WS/tmp/t1_render2_stdout.log" 2>/dev/null | tr -d '\r' | head -6
