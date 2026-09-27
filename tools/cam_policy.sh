#!/usr/bin/env bash
# What camera policies exist?  I need a FIXED, previously-approved pose rather than
# the auto trajectory_side framing the subagent used.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== camera module: policies and functions ==="
grep -n '^def \|policy\|"fixed"\|fixed' src/physim/camera/__init__.py | head -40 | sed 's/^/  /'

echo
echo "=== how policy is dispatched in pipeline ==="
grep -n 'policy\|perpendicular_camera\|build_camera\|camera_spec' src/physim/pipeline.py | head -20 | sed 's/^/  /'

echo
echo "=== _camera_config ==="
grep -n 'def _camera_config' -A25 src/physim/pipeline.py | sed 's/^/  /'

echo
echo "=== CameraSpec fields ==="
grep -rn 'class CameraSpec' -A20 src/physim/ | sed 's/^/  /'
