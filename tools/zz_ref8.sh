#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== x_rotation_degrees usage ==="
grep -rn "x_rotation_degrees\|visual_transform" "$R/src" "$R/scripts" "$R/tests" 2>/dev/null
echo
echo "=== import_scene.obj / axis_ usage ==="
grep -rn "import_scene\.obj\|axis_forward\|axis_up" "$R/src" "$R/scripts" "$R/tests" 2>/dev/null
echo
echo "=== how pybullet loads visual/collision ==="
grep -rn "visual_path\|loadURDF\|createVisualShape\|OBJ" "$R/src/physim/physics/pybullet_backend.py" | head -40
echo
echo "=== blender backend visual import ==="
grep -rn "visual\|obj\|import" "$R/src/physim/render/blender_backend.py" | head -60
