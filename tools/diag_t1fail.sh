#!/usr/bin/env bash
# Diagnose the fast rc=1 failures for rolling clips 2 and 3.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== error lines from t1_render.log ==="
grep -nE 'Error|Traceback|raise |RuntimeError|ValueError|KeyError|AssertionError|reasons=' \
  "$WS/tmp/t1_render.log" 2>/dev/null | tail -25 | cut -c1-260 | sed 's/^/  /'

echo
echo "=== last 30 lines of the log ==="
tail -30 "$WS/tmp/t1_render.log" 2>/dev/null | cut -c1-220 | sed 's/^/  /'

echo
echo "=== has any source file been modified recently? ==="
find "$REPO/src" -name '*.py' -newermt '-40 minutes' 2>/dev/null | sed 's/^/  /'
echo "  --- configs ---"
find "$REPO/configs" -name '*.yaml' -newermt '-40 minutes' 2>/dev/null | sed 's/^/  /'
