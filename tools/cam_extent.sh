#!/usr/bin/env bash
# How does the pipeline compute max_object_extent for the camera?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== pipeline: the camera call in prepare_sample ==="
sed -n '160,200p' src/physim/pipeline.py | sed 's/^/  /'

echo
echo "=== where is max_object_extent computed? ==="
grep -rn 'max_object_extent' src/ | sed 's/^/  /'

echo
echo "=== the camera's own guard ==="
grep -n 'Dynamic camera framing requires' -B12 src/physim/camera/__init__.py | sed 's/^/  /'
