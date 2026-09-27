#!/usr/bin/env bash
# How is polygon_xy derived, and does contains_xy fall back to bounds_xy?
# This decides whether placement stays inside the pinned rectangle now that
# collision is the full floor mesh.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== SurfaceSpec.contains_xy + polygon_xy ==="
sed -n '15,60p' "$REPO/src/physim/maps/__init__.py" | sed 's/^/  /'
echo
echo "=== _surface_spec: polygon_xy derivation ==="
sed -n '177,205p' "$REPO/src/physim/maps/__init__.py" | sed 's/^/  /'
