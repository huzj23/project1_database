#!/usr/bin/env bash
# ===========================================================================
# T1 production run: motions #1 #2 #3, 81 frames @ 1920x1080.
#
# 3 motions x 3 assets = 9 clips.  Each run is a fixed seed, variant x1.
# Validation is the gate: a sample that fails is reported, not repaired.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
LOG="$WS/tmp/t1_run.log"
: > "$LOG"

run_one () {
  local scen="$1" seed="$2" asset="$3"
  local dir="datasets/$scen/seed-$seed/x1"
  rm -rf "datasets/$scen/seed-$seed"
  local t0=$(date +%s)
  "$WS/tools/conda_env/bin/python" scripts/generate.py \
      --config configs/server.yaml --scenario "$scen" \
      --seed "$seed" --variant x1 --asset-id "$asset" \
      >> "$LOG" 2>&1
  local rc=$?
  local t1=$(date +%s)
  local verdict="MISSING"
  if [ -f "$dir/metadata.json" ]; then
    verdict=$("$WS/tools/conda_env/bin/python" -c "
import json
v=json.load(open('$dir/metadata.json')).get('validation',{})
print(('PASS' if v.get('valid') else 'FAIL') + ' ' + str(list(v.get('reasons',[]))))" 2>/dev/null)
  fi
  printf "T1 %-16s %-46s rc=%d %4ds  %s\n" "$scen" "$asset" "$rc" "$((t1-t0))" "$verdict"
}

echo "=== motion #1 rolling ==="
run_one rolling 1001 gso_whey_protein_vanilla
run_one rolling 1002 gso_room_essentials_fabric_cube_lavender
run_one rolling 1003 gso_ecoforms_plant_container_gp16a_coral

echo "=== motion #2 constant_force ==="
run_one constant_force 2001 gso_room_essentials_fabric_cube_lavender
run_one constant_force 2002 gso_whey_protein_vanilla
run_one constant_force 2003 gso_ecoforms_plant_container_gp16a_coral

echo "=== motion #3 free_fall ==="
run_one free_fall 3001 gso_down_to_earth_orchid_pot_ceramic_lime
run_one free_fall 3002 gso_ecoforms_plant_container_gp16a_coral
run_one free_fall 3003 gso_mad_gab_refresh_card_game

echo
echo "=== summary ==="
for s in rolling constant_force free_fall; do
  for d in datasets/$s/seed-*/x1; do
    [ -f "$d/metadata.json" ] || continue
    "$WS/tools/conda_env/bin/python" -c "
import json,sys
m=json.load(open('$d/metadata.json')); v=m.get('validation',{}); mt=v.get('metrics',{})
print('  %-46s valid=%-5s frames=%s' % ('$d', v.get('valid'), len(json.load(open('$d/trajectory.json')).get('trajectory',[]))))
" 2>/dev/null
  done
done
