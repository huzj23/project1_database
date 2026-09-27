#!/usr/bin/env bash
V=/data/raw/huzijian/project1_database/code/vendor/phyco-sim
echo "=== prepare_blender_object definition ==="
grep -rn "def prepare_blender_object" -A 40 "$V/kubric/kubric/renderer/blender_utils.py"
echo
echo "=== PyBullet FileBasedObject / loadURDF ==="
grep -rn "loadURDF\|FileBasedObject" "$V/kubric/kubric/simulator/pybullet.py" 2>/dev/null | head -30
echo
echo "=== kubric simulator dir ==="
ls "$V/kubric/kubric/simulator/" 2>/dev/null
