#!/usr/bin/env bash
# Isolate the depth layer as the crash source: run the same scenario with and
# without depth, at the size that failed.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

run_case() {
  local label="$1"; shift
  echo "=============================================================="
  echo "CASE $label : $*"
  "$PY" -X faulthandler "$WS/code/scenarios/run_single_object.py" "$@" 2>&1 |
    grep -E '\[phyco\]|Fatal Python error|phyco_common.py|run_single_object.py|Segmentation' |
    tail -8
  echo "CASE $label exit=${PIPESTATUS[0]}"
}

BASE=(--motion circular --object ball --frame_end 5 --resolution 320x180
      --samples 8 --scale 0.3 --output_dir "$WS/outcomes/_diag")

run_case no_depth  "${BASE[@]}" --layers image,segmentation --video_id d_nodepth
run_case with_depth "${BASE[@]}" --layers image,segmentation,depth --video_id d_withdepth
