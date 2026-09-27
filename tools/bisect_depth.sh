#!/usr/bin/env bash
# Bisect the depth-layer segfault: HDRI lighting vs analytic, depth vs z layer.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

run_case() {
  local label="$1"; shift
  "$PY" -X faulthandler "$WS/code/scenarios/run_single_object.py" "$@" >/dev/null 2>"$WS/tmp/err_$label.txt"
  local rc=$?
  local where
  where=$(grep -E 'phyco_common.py|run_single_object.py' "$WS/tmp/err_$label.txt" | head -1)
  printf '  %-22s rc=%-4s %s\n' "$label" "$rc" "$where"
}

BASE=(--motion circular --object ball --frame_end 3 --resolution 320x180
      --samples 8 --scale 0.3 --output_dir "$WS/outcomes/_diag")

echo "=== bisect ==="
run_case hdri_depth     "${BASE[@]}" --layers image,depth --hdri_random --video_id b1
run_case nohdri_depth   "${BASE[@]}" --layers image,depth --no_hdri     --video_id b2
run_case hdri_nodepth   "${BASE[@]}" --layers image       --hdri_random --video_id b3
run_case nohdri_nodepth "${BASE[@]}" --layers image       --no_hdri     --video_id b4
echo
echo "=== detail for hdri_depth (last lines) ==="
grep -E 'Fatal|phyco_common|Segmentation|\[phyco\]' "$WS/tmp/err_b1.txt" 2>/dev/null | tail -6 || echo "  (no error file)"
