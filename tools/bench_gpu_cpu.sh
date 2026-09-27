#!/usr/bin/env bash
# Production-settings speed comparison: is GPU actually faster than the 104-core
# CPU for these small scenes?  (Depth is excluded because the GPU depth pass
# segfaults in this bpy build; this measures the ceiling for GPU usefulness.)
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

bench() {
  local label="$1"; local gpu="$2"; local res="$3"; local spp="$4"; local frames="$5"
  KUBRIC_USE_GPU="$gpu" "$PY" "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --scale 0.3 --no_hdri \
    --layers image,segmentation \
    --frame_end "$((frames-1))" --resolution "$res" --samples "$spp" \
    --output_dir "$WS/outcomes/_bench" --video_id "b_$label" \
    >"$WS/tmp/bench_$label.log" 2>&1
  local rc=$?
  local t
  t=$(grep -oE '[0-9.]+s/frame' "$WS/tmp/bench_$label.log" | head -1)
  printf '  %-22s gpu=%-5s %s %sspp %2df  rc=%-4s %s\n' \
         "$label" "$gpu" "$res" "$spp" "$frames" "$rc" "${t:-?}"
}

echo "=== 768x432 / 64 spp / 12 frames ==="
bench gpu_prod  true  768x432 64 12
bench cpu_prod false 768x432 64 12
echo
echo "=== 768x432 / 32 spp / 12 frames ==="
bench gpu_32   true  768x432 32 12
bench cpu_32   false 768x432 32 12
