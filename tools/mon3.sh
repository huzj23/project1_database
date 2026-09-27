#!/usr/bin/env bash
# The `sed` on server.yaml turns out to be the ESTABLISHED pattern (t1_render.sh,
# t1c_render.sh, render_camC.sh all do it), so it is benign -- each runner sets it
# before it runs.  Check the backup for the canonical resting value, and monitor.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== tmp/server.yaml.bak ==="
if [ -f "$WS/tmp/server.yaml.bak" ]; then
  stat -c '  mtime %y' "$WS/tmp/server.yaml.bak"
  grep -n 'scenario_config\|samples_per_pixel\|frame_count' "$WS/tmp/server.yaml.bak" | sed 's/^/  /'
else
  echo "  absent"
fi

echo
echo "=== red-wood render status ==="
cat "$WS/tmp/ttwood_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "  running: $(pgrep -af 'scripts/generate.py' | grep -v 'bash -c' | head -1 | cut -c1-110)"
echo "  elapsed: $(ps -o etime= -p $(pgrep -f 'scripts/generate.py' | head -1) 2>/dev/null | tr -d ' ')"
echo "  --- all turntable clips ---"
for d in "$REPO"/datasets/turntable_*/seed-*/x1; do
  [ -d "$d" ] || continue
  printf "    %-42s rgb=%-3s mp4=%s\n" "$(echo $d | sed "s|$REPO/datasets/||")" \
    "$(ls $d/rgb 2>/dev/null | wc -l)" "$([ -f $d/video.mp4 ] && echo yes || echo no)"
done
