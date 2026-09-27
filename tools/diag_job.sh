#!/usr/bin/env bash
# Re-run a single job and surface only the non-render output (i.e. the error).
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" "$WS/code/scenarios/run_single_object.py" \
  --motion circular --object ball --frame_end 3 --resolution 320x180 \
  --samples 8 --threads 4 --save_mp4 --qa_sheet --hdri_random \
  --output_dir "$WS/outcomes/_diag" --video_id diagx 2>&1 |
  grep -vE '^Fra:|^Saved:|^ ?Time:|^ *$|^Fra' |
  tail -30
echo "---- exit=${PIPESTATUS[0]} ----"
