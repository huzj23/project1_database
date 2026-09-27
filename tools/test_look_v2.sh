#!/usr/bin/env bash
# Integration test of the improved look pipeline:
#   1280x720 / PNG lossless / motion blur / studio cyclorama / 3-point softbox
#   / Poly Haven PBR concrete floor / HDRI empty_warehouse_01 (reference recipe)
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

echo "=== look=studio, 1280x720, PNG, 12 frames ==="
"$PY" -X faulthandler "$WS/code/scenarios/run_single_object.py" \
  --motion circular --object ball --radius 1.2 --period 2.0 --scale 0.3 \
  --look studio --floor_material concrete_floor_worn_001 \
  --resolution 1280x720 --samples 32 --frame_end 11 \
  --frame_format png --motion_blur 0.25 --focal_length 55 \
  --output_dir "$WS/outcomes/_look_v2" --video_id studio_test \
  2>&1 | grep -E '\[phyco\]|Error|Traceback|phyco_' | tail -20

echo
echo "=== artifacts ==="
ls -la "$WS/outcomes/_look_v2/studio_test" 2>/dev/null | head -8
echo "  frame count: $(ls "$WS/outcomes/_look_v2/studio_test"/rgba_*.png 2>/dev/null | wc -l)"
du -sh "$WS/outcomes/_look_v2/studio_test" 2>/dev/null | sed 's/^/  /'
