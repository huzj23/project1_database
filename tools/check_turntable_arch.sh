#!/usr/bin/env bash
# ===========================================================================
# CRITICAL ARCHITECTURAL CHECK for motions #5/#6 (turntable).
#
# The physics backend builds exactly ONE dynamic body:
#     simulated_object = kb.Sphere / FileBasedObject / Cube ...
# The turntable needs a SECOND dynamic body (the disc) plus a drive mechanism.
# Does the pipeline's architecture allow that at all?
#
# Also: does the Blender render path replay only ONE trajectory?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== how many dynamic bodies does the backend create? ==="
grep -n 'kb.Sphere\|kb.Cube\|kb.FileBasedObject\|scene +=' \
    "$REPO/src/physim/physics/pybullet_backend.py" | sed 's/^/  /'

echo
echo "=== what does simulate() return? (trajectory of how many bodies?) ==="
sed -n '160,197p' "$REPO/src/physim/physics/pybullet_backend.py" | sed 's/^/  /'

echo
echo "=== render backend: how many objects does it replay? ==="
grep -n 'def render\|linked_objects\|keyframe_insert\|trajectory' \
    "$REPO/src/physim/render/blender_backend.py" | head -25 | sed 's/^/  /'
