#!/usr/bin/env bash
# CONFIRM the proper fix mechanism exists: mesh-collision regions.
# classroom/street already declare `collision: type: mesh` with an extracted
# static URDF.  That is the mentor's own pattern (generate_environment_surface_collision.py).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== a mesh-collision region (classroom desk) as the template ==="
sed -n '50,70p' "$REPO/configs/maps.yaml" | sed 's/^/  /'

echo
echo "=== the extraction tool's CLI ==="
grep -n 'add_argument\|def main\|__doc__' -A2 "$REPO/scripts/generate_environment_surface_collision.py" 2>/dev/null | head -40 | sed 's/^/  /'

echo
echo "=== how _surface_spec resolves a mesh collision ==="
sed -n '204,245p' "$REPO/src/physim/maps/__init__.py" | sed 's/^/  /'
