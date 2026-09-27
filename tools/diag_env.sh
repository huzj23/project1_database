#!/usr/bin/env bash
# The subject renders but the apartment does not.  Check what the render backend
# actually did with the environment visual.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
LOG="$WS/log/p1_smoke.log"

echo "=== environment-related log lines ==="
grep -inE 'environment|scene\.glb|blend|import|visual|hidden|hide_viewport|hide_render' "$LOG" 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=== what build_scene does with the environment ==="
sed -n '60,140p' "$REPO/src/physim/render/blender_backend.py" | sed 's/^/  /'
