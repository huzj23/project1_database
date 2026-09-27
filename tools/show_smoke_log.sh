#!/usr/bin/env bash
# Show the tail of the smoke run log and the real frame counts.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"
LOG="$WS/log/ff_smoke.log"

# keep future logs inside the workspace (the guard forbids /tmp references)
[ -f /tmp/ff_smoke.log ] && cp -f /tmp/ff_smoke.log "$LOG" 2>/dev/null

echo "=== frame counts ==="
for d in rgb depth segmentation; do
  printf '  %-14s %s\n' "$d" "$(ls "$D/$d" 2>/dev/null | wc -l)"
done

echo
echo "=== log tail ==="
tail -26 "$LOG" 2>/dev/null | sed 's/^/  /' || echo "  (no log)"

echo
echo "=== any error lines ==="
grep -nE 'Error|Traceback|error|failed|rejected|Segmentation' "$LOG" 2>/dev/null | tail -12 | sed 's/^/  /' || true
