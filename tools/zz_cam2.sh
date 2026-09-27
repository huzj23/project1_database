#!/usr/bin/env bash
C=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/src/physim/camera/__init__.py
echo "=== perpendicular_camera ==="
sed -n '75,200p' "$C"
echo "=== object_frame_fraction occurrences ==="
grep -n 'object_frame_fraction\|max_object_extent\|radius' "$C"
