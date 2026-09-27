#!/usr/bin/env bash
# Validate the clamped auto-framing: one rotation case (subject spins in place,
# where the old fixed 5.5 m camera made it a speck) and one circular case
# (2.4 m trajectory, where the cap must still keep the cyclorama visible).
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_framing2"
rm -rf "$OUT"

run() {
  local tag="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --look studio --resolution 1280x720 --samples 24 --frame_end 3 \
    --frame_format png --motion_blur 0.25 --focal_length 55 \
    --output_dir "$OUT" --video_id "$tag" "$@" 2>&1 |
    grep -E 'camera framed|rendered|FAILED|Error' | sed 's/^/    /'
}

echo "=== rotation (was 7.5% of frame width at fixed 5.5 m) ==="
run rot_jenga --motion rotation --object jenga --spin_axis z --spin_period 2.0 --scale 0.60
echo "=== rotation, brick ==="
run rot_brick --motion rotation --object brick_box --spin_axis y --spin_period 2.0 --scale 0.60
echo "=== circular (trajectory must still fit, backdrop still visible) ==="
run circ_ball --motion circular --object ball --radius 1.2 --period 2.0 --scale 0.45
echo "=== damped ==="
run damp_brick --motion damped --object brick_box --speed 3.5 --linear_damping 0.8 --scale 0.60

echo
for d in "$OUT"/*/; do
  n=$(basename "$d")
  cp -f "$d/rgba_00002.png" "$OUT/frame_$n.png" 2>/dev/null && echo "  frame_$n.png"
done
