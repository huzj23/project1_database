#!/usr/bin/env bash
V=/data/raw/huzijian/project1_database/code/vendor/phyco-sim
echo "=== vendor kubric renderer files ==="
find "$V/kubric" -name '*.py' -path '*renderer*' -printf '%p\n' 2>/dev/null
echo "=== grep import_scene.obj in vendor ==="
grep -rn "import_scene.obj" "$V" 2>/dev/null | head -20
echo "=== grep axis_forward in vendor ==="
grep -rn "axis_forward" "$V" 2>/dev/null | head -20
echo "=== grep FileBasedObject render_filename load ==="
grep -rn "render_filename\|load_obj\|bpy.ops.import" "$V/kubric/renderer/blender.py" 2>/dev/null | head -30
echo "=== dataset turntable_carry seed-005001 config.yaml ==="
sed -n '1,60p' /data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1/config.yaml
echo "=== rgb frame listing ==="
ls /data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1/rgb/ 2>/dev/null | head -5
