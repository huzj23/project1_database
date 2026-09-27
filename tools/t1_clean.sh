#!/usr/bin/env bash
# Kill ALL competing renders, then relaunch exactly one clean T1 render.
#
# Two generate.py processes were writing the same cache dir (one left from the
# stopped tmux session, one from the probe).  Concurrent writers are the
# stale-frame hazard, so clear both and start over with the fixed lighting.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== killing all generate.py / blender ==="
pkill -9 -f "generate.py" 2>/dev/null
pkill -9 -f "blender" 2>/dev/null
tmux kill-session -t t1 2>/dev/null
tmux kill-session -t t1probe 2>/dev/null
sleep 3
echo "  remaining generate.py: $(pgrep -cf generate.py)"
echo "  remaining blender:     $(pgrep -cf blender)"

echo
echo "=== clear stale cache + partial datasets ==="
rm -rf "$REPO/cache/rolling" "$REPO/cache/constant_force" "$REPO/cache/free_fall"
rm -rf "$REPO/datasets/rolling" "$REPO/datasets/constant_force"
echo "  cache: $(ls "$REPO/cache" 2>/dev/null | tr '\n' ' ')"
echo "  datasets: $(ls "$REPO/datasets" 2>/dev/null | tr '\n' ' ')"

echo
echo "=== relaunch ONE clean T1 render ==="
tmux new-session -d -s t1 "bash $WS/tools/t1_render.sh > $WS/tmp/t1_render_stdout.log 2>&1"
sleep 5
tmux ls 2>/dev/null | grep -E '^t1:' | sed 's/^/  /'
pgrep -af "generate.py" | head -2 | sed 's/^/  /'
