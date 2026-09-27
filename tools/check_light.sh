#!/usr/bin/env bash
# ===========================================================================
# IRON RULE 4 CHECK.
#
# The rolling render printed:
#     environment_lighting_source: 'asset_fallback'
#     environment_light_count: 1
#     environment_light_types: ['AREA']
#     environment_authored_world: None
#
# V3.3 section 4 froze the scene as having SEVEN authored POINT lights in the
# `authored_lighting` collection.  If the renderer fell back to a single AREA
# light, the picture is NOT lit by the scene author's configuration and iron
# rule 4 is violated.
#
# Find out exactly what the renderer looks for and what it found.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== how is environment_lighting_source decided? ==="
grep -n 'lighting_source\|authored_lighting\|asset_fallback\|authored_world\|environment_light_count' \
  src/physim/render/blender_backend.py | sed 's/^/  /'

echo
echo "=== the lighting block in context ==="
grep -n 'lighting_source' -B12 -A25 src/physim/render/blender_backend.py | head -70 | sed 's/^/  /'
