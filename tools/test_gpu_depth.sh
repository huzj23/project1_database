#!/usr/bin/env bash
# Is the depth-layer crash tied to GPU (Cycles/CUDA) rendering?
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

run_case() {
  local label="$1"; local gpu="$2"
  KUBRIC_USE_GPU="$gpu" "$PY" -X faulthandler \
    "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --frame_end 5 --resolution 320x180 \
    --samples 8 --scale 0.3 --layers image,segmentation,depth \
    --no_hdri --output_dir "$WS/outcomes/_diag" --video_id "gpu_$label" \
    >"$WS/tmp/gpu_$label.log" 2>&1
  local rc=$?
  local where
  where=$(grep -E 'phyco_common.py|Fatal Python error' "$WS/tmp/gpu_$label.log" | head -1)
  printf '  %-10s rc=%-4s %s\n' "$label" "$rc" "$where"
}

echo "=== GPU vs CPU depth rendering ==="
run_case gpu true
run_case cpu false
echo
echo "=== timing from the successful(?) runs ==="
grep -hE '\[phyco\] rendered' "$WS/tmp/gpu_gpu.log" "$WS/tmp/gpu_cpu.log" 2>/dev/null | sed 's/^/  /'
