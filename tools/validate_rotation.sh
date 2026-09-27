#!/usr/bin/env bash
# Complete the framing validation set: rotation case (subject spins in place).
# Runs under tmux so it survives the local machine going away entirely.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_framing3"
mkdir -p "$OUT"

run() {
  local tag="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --look studio --resolution 1280x720 --samples 16 --frame_end 23 \
    --frame_format png --motion_blur 0.25 --focal_length 55 --qa_sheet \
    --output_dir "$OUT" --video_id "$tag" "$@" 2>&1 |
    grep -E 'camera framed|rendered|FAILED'
}

echo "[validate] rotation jenga"
run rot_jenga --motion rotation --object jenga --spin_axis z --spin_period 2.0 --scale 0.60
echo "[validate] rotation brick_box"
run rot_brick --motion rotation --object brick_box --spin_axis y --spin_period 2.0 --scale 0.60

echo
for d in "$OUT"/*/; do
  n=$(basename "$d")
  [ -f "$d/qa_contact_sheet.jpg" ] && cp -f "$d/qa_contact_sheet.jpg" "$OUT/qa_$n.jpg" && echo "  qa_$n.jpg"
done
echo "[validate] done $(date '+%F %T')"
