#!/usr/bin/env bash
# Where are the rendered frames going, and how far along is the probe?
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-1001/x1"

echo "=== is the render still alive? ==="
pgrep -af "generate.py" | head -3
tmux ls 2>/dev/null | grep -E 't1probe' || echo "  no t1probe session"

echo
echo "=== sample dir tree ==="
find "$D" -maxdepth 2 -type d 2>/dev/null | sed 's/^/  /'
echo "  files:"
find "$D" -type f 2>/dev/null | head -20 | sed 's/^/    /'
echo "  counts per dir:"
for sub in rgb depth segmentation; do
  n=$(ls "$D/$sub" 2>/dev/null | wc -l)
  echo "    $sub: $n"
done

echo
echo "=== scratch dirs (frames may be staged here) ==="
ls -dt /tmp/*scratch* /tmp/*physim* /tmp/tmp* 2>/dev/null | head -5 | while read d; do
  echo "  $d: $(ls $d 2>/dev/null | wc -l) entries"
done

echo
echo "=== last log lines ==="
tail -6 "$WS/tmp/probe_render.log" 2>/dev/null | sed 's/^/  /'
