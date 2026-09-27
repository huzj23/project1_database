#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== third_party layout ==="
ls -la "$R/third_party/"
ls -la "$R/third_party/phyco-sim/" 2>/dev/null | head -30
echo "=== find kubric blender renderer ==="
find "$R/third_party" -name 'blender.py' -path '*renderer*' -printf '%p\n' 2>/dev/null
echo "=== grep import_scene.obj inside third_party ==="
grep -rn "import_scene.obj" "$R/third_party" 2>/dev/null | head -20
echo "=== grep axis_forward inside third_party ==="
grep -rn "axis_forward" "$R/third_party" 2>/dev/null | head -20
echo "=== dataset turntable_carry seed-005001 tree ==="
find "$R/datasets/turntable_carry/seed-005001" -maxdepth 3 -printf '%y %10s %p\n' | sort -k3 | head -40
