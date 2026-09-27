#!/usr/bin/env bash
# Full-clip framing validation (24 frames) with QA contact sheets, so we can see
# whether the subject stays inside the frame for the WHOLE trajectory -- the
# single-frame check cannot show that.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_framing3"
rm -rf "$OUT"

run() {
  local tag="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --look studio --resolution 1280x720 --samples 16 --frame_end 23 \
    --frame_format png --motion_blur 0.25 --focal_length 55 --qa_sheet \
    --output_dir "$OUT" --video_id "$tag" "$@" 2>&1 |
    grep -E 'camera framed|rendered|FAILED' | sed 's/^/    /'
}

echo "=== circular r=1.2 (trajectory 2.4 m -- must stay in frame) ==="
run circ_r12 --motion circular --object ball --radius 1.2 --period 2.0 --scale 0.45
echo "=== circular r=0.8 ==="
run circ_r08 --motion circular --object ball --radius 0.8 --period 2.0 --scale 0.45
echo "=== damped (travel 4.4 m) ==="
run damp_s35 --motion damped --object brick_box --speed 3.5 --linear_damping 0.8 --scale 0.60
echo "=== rotation jenga ==="
run rot_jenga --motion rotation --object jenga --spin_axis z --spin_period 2.0 --scale 0.60

echo
for d in "$OUT"/*/; do
  n=$(basename "$d")
  cp -f "$d/qa_contact_sheet.jpg" "$OUT/qa_$n.jpg" 2>/dev/null && echo "  qa_$n.jpg"
done
