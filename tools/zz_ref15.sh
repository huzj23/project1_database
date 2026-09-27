#!/usr/bin/env bash
V=/data/raw/huzijian/project1_database/code/vendor/phyco-sim
echo "=== where does the blender renderer set object rotation/quaternion? ==="
grep -n "quaternion\|rotation_mode\|rotation_euler\|matrix_world\|location" "$V/kubric/kubric/renderer/blender.py" | head -50
echo
echo "=== blender_utils: any rotation handling ==="
grep -n "quaternion\|rotation\|location\|scale" "$V/kubric/kubric/renderer/blender_utils.py" | head -40
