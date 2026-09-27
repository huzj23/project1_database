#!/usr/bin/env bash
C=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/src/physim/camera/__init__.py
grep -n 'class CameraSpec' -A 30 "$C"
echo "=== fixed_camera ==="
grep -n 'def fixed_camera' -A 40 "$C"
