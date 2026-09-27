#!/usr/bin/env bash
# ===========================================================================
# Extend the fast preflight to also exercise the CAMERA solver.
#
# Rolling clips 2 and 3 died after 5 s with
#     ValueError: A static camera cannot fit the complete trajectory while
#     keeping the largest object visible: projected fraction 0.0907, minimum 0.1000
# The physics had PASSED -- the failure is in perpendicular_camera, which pulls
# the camera back far enough to frame the whole trajectory and then finds the
# object's projected size below min_object_frame_fraction (0.10).
#
# My preflight9.sh only ran sample→simulate→validate, so it could not catch this.
# Add the camera call so a framing failure costs 1 s instead of 23 min.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== the camera failure site ==="
sed -n '120,165p' src/physim/camera/__init__.py | sed 's/^/  /'

echo
echo "=== how pipeline calls it ==="
sed -n '175,195p' src/physim/pipeline.py | sed 's/^/  /'
