#!/usr/bin/env bash
# Full elchk log + wood render progress.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
echo "=== elchk.log FULL (unfiltered - filtering hides tracebacks) ==="
cat "$WS/tmp/elchk.log" 2>/dev/null | tr -d '\r' | tail -40 | sed 's/^/  /'
echo
echo "=== elchk tmux still alive? ==="
tmux ls 2>/dev/null | sed 's/^/  /'
echo
echo "=== wood render: which clip / how far ==="
cat "$WS/tmp/ttwood_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
for d in "$REPO"/cache/turntable_carry/seed-005001/x1/images; do
  [ -d "$d" ] && echo "  current clip staged: $(ls $d | wc -l)/81 frames"
done
echo "  render log tail:"
tail -3 "$WS/tmp/tt_wood_render.log" 2>/dev/null | cut -c1-170 | sed 's/^/    /'
echo "  elapsed: $(ps -o etime= -p $(pgrep -f 'scripts/generate.py' | head -1) 2>/dev/null)"
