#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01: render ONE real frame through the PATCHED chain and prove the
# sentinel frame is quarantined (not deleted).
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$REPO" || exit 1

echo "=== blender check ==="
"$BLENDER" --version 2>&1 | head -1

echo
echo "=== running the render regression under Blender ==="
"$BLENDER" --background --factory-startup \
  --python "$WS/tools/v55_regression_purge.py" 2>&1 | \
  grep -v '^Blender quit' | tail -45
