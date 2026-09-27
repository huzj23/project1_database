#!/usr/bin/env bash
# Test the ReplicaCAD interior backdrop (Track B1).
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

echo "=== available stages ==="
ls "$WS/models/backgrounds/replicad/stages" 2>/dev/null | sed 's/^/  /'

run() {
  local tag="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --radius 1.0 --period 2.0 --scale 0.45 \
    --look interior --resolution 1280x720 --samples 24 --frame_end 5 \
    --frame_format png --motion_blur 0.25 --focal_length 55 \
    --output_dir "$WS/outcomes/_interior" --video_id "$tag" "$@" 2>&1 |
    grep -E 'backdrop|stage bounds|camera framed|rendered|DONE|FAILED|Error' | sed 's/^/  /'
}

echo
echo "=== frl_apartment_stage, d=4.5 e=14 az=-55 ==="
run frl_d45 "$@"
echo
echo "=== copy mid frame ==="
cp -f "$WS/outcomes/_interior/frl_d45/rgba_00003.png" "$WS/outcomes/_interior/frame_frl.png" 2>/dev/null &&
  echo "  wrote $WS/outcomes/_interior/frame_frl.png"
