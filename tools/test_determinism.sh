#!/usr/bin/env bash
# Is the depth segfault deterministic, or a race?  Run the same command 4 times
# and also re-run the exact smoke configuration 2 times.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

rep() {
  local label="$1"; shift
  local pass=0 fail=0
  for i in 1 2 3 4; do
    "$PY" "$WS/code/scenarios/run_single_object.py" "$@" \
      --output_dir "$WS/outcomes/_diag" --video_id "r_${label}_$i" \
      >"$WS/tmp/r_${label}_$i.log" 2>&1
    if [ $? -eq 0 ]; then pass=$((pass+1)); else fail=$((fail+1)); fi
  done
  printf '  %-18s pass=%d fail=%d\n' "$label" "$pass" "$fail"
}

echo "--- small config, depth, 4 repetitions ---"
rep small_depth --motion circular --object ball --frame_end 3 \
    --resolution 320x180 --samples 8 --layers image,segmentation,depth --hdri_random

echo "--- small config, NO depth, 4 repetitions (control) ---"
rep small_nodepth --motion circular --object ball --frame_end 3 \
    --resolution 320x180 --samples 8 --layers image,segmentation --hdri_random

echo "--- production config, depth, 2 repetitions ---"
rep prod_depth --motion circular --object ball --frame_end 5 \
    --resolution 768x432 --samples 64 --layers image,segmentation,depth --hdri_random

echo
echo "--- load during test: $(uptime | sed 's/.*load average/load average/') ---"
