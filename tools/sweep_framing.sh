#!/usr/bin/env bash
# Framing sweep for the studio look: pick the composition that best matches the
# reference (subject plus floor and back wall, product-shot feel).
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_framing"
rm -rf "$OUT"

run() {
  local tag="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --radius 1.2 --period 2.0 --scale 0.3 \
    --look studio --floor_material concrete_floor_worn_001 \
    --resolution 1280x720 --samples 24 --frame_end 5 \
    --frame_format png --motion_blur 0.25 --focal_length 55 \
    --output_dir "$OUT" --video_id "$tag" "$@" >/dev/null 2>&1
  local rc=$?
  printf '  %-22s rc=%s\n' "$tag" "$rc"
}

echo "=== framing variants (elev, target_z, distance) ==="
run e12_t09_d55  --camera_elevation 12 --camera_target_z 0.9 --camera_distance 5.5
run e16_t10_d45  --camera_elevation 16 --camera_target_z 1.0 --camera_distance 4.5
run e10_t07_d70  --camera_elevation 10 --camera_target_z 0.7 --camera_distance 7.0

echo
echo "=== copy mid frames out for review ==="
for d in "$OUT"/*/; do
  n=$(basename "$d")
  cp -f "$d/rgba_00003.png" "$OUT/frame_$n.png" 2>/dev/null && echo "  $OUT/frame_$n.png"
done
