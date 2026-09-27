#!/usr/bin/env bash
# ===========================================================================
# Dump the exact blender_backend material call sites so the patch is precise.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== every apply_declared_material / material reference in blender_backend.py ==="
grep -n 'material\|MaterialSpec\|import' src/physim/render/blender_backend.py | sed 's/^/  /'

echo
echo "=== the surrounding block (lines 300-360) ==="
sed -n '300,365p' src/physim/render/blender_backend.py | cat -n | sed 's/^/  /'

echo
echo "=== ScenarioSample fields ==="
grep -n 'class ScenarioSample' -A 40 src/physim/scenarios/__init__.py | sed 's/^/  /'
