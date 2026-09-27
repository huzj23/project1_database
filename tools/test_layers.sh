#!/usr/bin/env bash
# 1) Which layer combination breaks GPU rendering?
# 2) How fast is CPU rendering at production settings (104 cores available)?
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

run_layers() {
  local label="$1"; local gpu="$2"; local layers="$3"; shift 3
  KUBRIC_USE_GPU="$gpu" "$PY" -X faulthandler \
    "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --scale 0.3 --no_hdri \
    --layers "$layers" --output_dir "$WS/outcomes/_diag" \
    --video_id "lay_$label" "$@" >"$WS/tmp/lay_$label.log" 2>&1
  local rc=$?
  local t
  t=$(grep -oE 'rendered [0-9]+ frames in [0-9.]+s \([0-9.]+s/frame\)' "$WS/tmp/lay_$label.log" | head -1)
  printf '  %-26s rc=%-4s %s\n' "$label" "$rc" "${t:-<no render line>}"
}

echo "=== which GPU layer combos work (320x180, 6 frames) ==="
run_layers gpu_rgba_seg   true  "image,segmentation"                --frame_end 5 --resolution 320x180 --samples 8
run_layers gpu_rgba_depth true  "image,depth"                       --frame_end 5 --resolution 320x180 --samples 8
run_layers gpu_depth_only true  "depth"                             --frame_end 5 --resolution 320x180 --samples 8
run_layers gpu_all        true  "image,segmentation,depth"          --frame_end 5 --resolution 320x180 --samples 8
run_layers cpu_all        false "image,segmentation,depth"          --frame_end 5 --resolution 320x180 --samples 8

echo
echo "=== CPU at production settings (768x432, 64 spp, 24 frames) ==="
run_layers cpu_prod       false "image,segmentation,depth"          --frame_end 23 --resolution 768x432 --samples 64
