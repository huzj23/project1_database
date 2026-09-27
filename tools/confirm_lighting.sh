#!/usr/bin/env bash
# Confirm the lighting/depth interaction on an otherwise idle machine.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

echo "--- machine load: $(uptime | sed 's/.*load average/load average/') ---"

run_case() {
  local label="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --frame_end 3 --resolution 320x180 \
    --samples 8 --output_dir "$WS/outcomes/_diag" --video_id "c_$label" \
    "$@" >"$WS/tmp/c_$label.log" 2>&1
  local rc=$?
  printf '  %-24s rc=%-5s\n' "$label" "$rc"
}

echo "--- lighting x depth matrix ---"
run_case hdri_depth       --layers image,depth --hdri_random
run_case hdri_nodepth     --layers image       --hdri_random
run_case anallight_depth  --layers image,depth --no_hdri
run_case anallight_nodepth --layers image      --no_hdri
run_case hdri_all         --layers image,segmentation,depth --hdri_random
run_case anallight_all    --layers image,segmentation,depth --no_hdri

echo
echo "--- what crashed (if anything) ---"
for f in "$WS"/tmp/c_*.log; do
  [ -f "$f" ] || continue
  n=$(basename "$f" .log)
  grep -qE 'Fatal Python error|Segmentation' "$f" && echo "  CRASH: $n"
done
echo "  (end)"
