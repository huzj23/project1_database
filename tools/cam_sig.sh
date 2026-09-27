#!/usr/bin/env bash
# Get the exact perpendicular_camera signature and the pipeline's call site.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== signature ==="
grep -n 'def perpendicular_camera' -A12 src/physim/camera/__init__.py | sed 's/^/  /'

echo
echo "=== pipeline call site (full context) ==="
sed -n '195,235p' src/physim/pipeline.py | sed 's/^/  /'

echo
echo "=== what prepare_sample receives ==="
grep -n 'def prepare_sample' -A22 src/physim/pipeline.py | sed 's/^/  /'
