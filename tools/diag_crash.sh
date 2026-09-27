#!/usr/bin/env bash
# Reproduce the post-render segfault in the foreground with faulthandler enabled,
# so we get a Python-level stack at the point of the crash.
source /data/raw/huzijian/project1_database/tools/server_env.sh

PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

echo "=== env sanity ==="
echo "TMPDIR            = $TMPDIR"
echo "LD_LIBRARY_PATH   = $LD_LIBRARY_PATH"
echo "CUDA_VISIBLE_DEVICES = $CUDA_VISIBLE_DEVICES"
echo "KUBRIC_USE_GPU    = $KUBRIC_USE_GPU"

echo
echo "=== run one scenario with faulthandler ==="
"$PY" -X faulthandler "$WS/code/scenarios/run_single_object.py" \
  --motion circular --object ball --frame_end 5 \
  --resolution 320x180 --samples 8 --scale 0.3 \
  --output_dir "$WS/outcomes/_diag" --video_id diag1 2>&1 | tail -45

echo
echo "exit=$?"
