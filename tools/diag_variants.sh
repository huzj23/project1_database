#!/usr/bin/env bash
# The same scenario passed the smoke test at 02:59 and segfaults now.
# Compare variants to find what changed: thread count, and leftover machine load.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

echo "--- machine state ---"
uptime | sed 's/^/  /'
free -g | head -2 | sed 's/^/  /'
echo "  my python procs: $(ps -eo cmd 2>/dev/null | grep -c '[c]onda_env/bin/python')"
echo "  tmp scratch dirs: $(ls -1 "$WS/tmp" 2>/dev/null | grep -c phyco_scratch)"

run_variant() {
  local label="$1"; shift
  "$PY" "$WS/code/scenarios/run_single_object.py" \
    --motion circular --object ball --frame_end 3 --resolution 320x180 \
    --samples 8 --no_hdri --output_dir "$WS/outcomes/_diag" \
    --video_id "v_$label" "$@" >"$WS/tmp/v_$label.log" 2>&1
  local rc=$?
  local t
  t=$(grep -oE 'rendered [0-9]+ frames[^)]*\)' "$WS/tmp/v_$label.log" | head -1)
  printf '  %-16s rc=%-5s %s\n' "$label" "$rc" "$t"
}

echo
echo "--- variants (all with depth layer) ---"
run_variant threads4     --layers image,segmentation,depth --threads 4
run_variant threads52    --layers image,segmentation,depth --threads 52
run_variant nothreads    --layers image,segmentation,depth
run_variant nodepth      --layers image,segmentation      --threads 4
