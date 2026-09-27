#!/usr/bin/env bash
# Diagnose why the second smoke run produced no metadata.json.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"

echo "=== sample dir ==="
if [ -d "$D" ]; then
  find "$D" -maxdepth 1 | sed "s#$D#  .#" | head -14
  for sub in rgb depth segmentation; do
    printf '  %-14s %s frames\n' "$sub" "$(ls "$D/$sub" 2>/dev/null | wc -l)"
  done
else
  echo "  (missing entirely)"
fi

echo
echo "=== newest log ==="
LOG=$(ls -t "$WS"/log/ff_smoke.log 2>/dev/null | head -1)
if [ -n "$LOG" ]; then
  echo "  $LOG"
  grep -nE 'Error|Traceback|FileExists|valid=|SAMPLE_OUTPUT|rejected' "$LOG" | tail -10 | sed 's/^/  /'
  echo "  --- tail ---"
  tail -6 "$LOG" | sed 's/^/  /'
fi

echo
echo "=== did the physics run at all? (look for validation output) ==="
grep -oE "valid=(True|False)[^,]*" "$LOG" 2>/dev/null | tail -3 | sed 's/^/  /' || echo "  none found"
