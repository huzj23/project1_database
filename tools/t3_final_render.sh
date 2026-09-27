#!/usr/bin/env bash
# ===========================================================================
# RENDER the 4 turntable clips (#5 环形转动 x2, #6 转盘上的转动 x2).
#
# Everything below is already measured, not assumed:
#   * actor = gso_sootheze_cold_therapy_elephant ("小熊"), as requested
#   * camera = the APPROVED fixed pose (0.934,-0.485,1.1784)->(0.414,0.175,0.8084),
#     50 mm, copied from tools/tt_on_table.sh; `fixed` policy so it cannot drift
#   * #5 omega 1.20-1.30, orbit 0.50-0.55 -> arc 345-365 deg (a real full ring)
#   * #6 omega 1.20-1.30, orbit 0.15-0.25 -> arc 345-365 deg, near-axis co-rotation
#   * 20/20 seeds screened PASS on physics + in-frame + disc rotation
#
# Each clip renders through its OWN server config so configs/server.yaml (used by
# the other render runner) is never written here.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
LOG="$WS/tmp/t3_final.log"
: > "$LOG"

run_one () {
  local scen="$1" cfg="$2" seed="$3"
  local padded; padded=$(printf "seed-%06d" "$seed")
  local dir="datasets/$scen/$padded/x1"
  rm -rf "datasets/$scen/$padded"
  local t0; t0=$(date +%s)
  "$WS/tools/conda_env/bin/python" scripts/generate.py \
      --config "configs/server_turntable_${cfg}.yaml" \
      --seed "$seed" --variant x1 \
      --asset-id gso_sootheze_cold_therapy_elephant >> "$LOG" 2>&1
  local rc=$?
  local t1; t1=$(date +%s)
  local n=0; [ -d "$dir/rgb" ] && n=$(ls "$dir/rgb" 2>/dev/null | wc -l)
  local v="MISSING"
  if [ -f "$dir/metadata.json" ]; then
    v=$("$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('$dir/metadata.json')); x=m.get('validation',{})
print(('PASS' if x.get('valid') else 'FAIL')+' '+str(list(x.get('reasons',[]))))" 2>/dev/null)
  fi
  printf "T3 %-16s %-6s rc=%d %5ds rgb=%d %s\n" "$scen" "$seed" "$rc" "$((t1-t0))" "$n" "$v"
}

echo "=== #5 环形转动 (turntable_carry) ==="
run_one turntable_carry carry 5001
run_one turntable_carry carry 5002

echo "=== #6 转盘上的转动 (turntable_spin) ==="
run_one turntable_spin spin 5001
run_one turntable_spin spin 5002

echo "=== T3 FINAL DONE ==="
