#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== object_extent ==="
grep -n 'def object_extent' -A 25 "$R/src/physim/scenarios/common.py"
echo
echo "=== camera policy dispatch ==="
grep -n 'policy\|fixed_camera\|perpendicular_camera\|trajectory_side' "$R/src/physim/camera/__init__.py" | head -30
echo
echo "=== pipeline camera usage ==="
grep -n 'camera\|policy' "$R/src/physim/pipeline.py" | head -40
