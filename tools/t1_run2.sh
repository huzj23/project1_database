#!/usr/bin/env bash
# ===========================================================================
# T1 runner, CORRECTED.
#
# Root cause of the rc=1 failures: `--scenario X` makes load_run_config replace
# `project.scenario_config` with configs/scenarios/X.yaml -- the MENTOR's default
# config, which selects his maps (basketball_court / classroom / street).  Those
# have no visual assets on disk (V3.3 §6), so every run died with
# FileNotFoundError: .../street/visual/scene.blend.
#
# Correct invocation: write the scenario file we want into server.yaml's
# `project.scenario_config`, then call generate.py WITHOUT --scenario.
#
# Also: `--asset-id` is honoured, so each run pins its actor explicitly.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
LOG="$WS/tmp/t1_run.log"
: > "$LOG"

set_scenario () {
  sed -i "s|^  scenario_config: .*|  scenario_config: configs/scenarios/$1.yaml|" configs/server.yaml
}

run_one () {
  local scen="$1" seed="$2" asset="$3" cfg="$4"
  set_scenario "$cfg"
  local dir="datasets/$scen/seed-$seed/x1"
  rm -rf "datasets/$scen/seed-$seed"
  local t0=$(date +%s)
  "$WS/tools/conda_env/bin/python" scripts/generate.py \
      --config configs/server.yaml \
      --seed "$seed" --variant x1 --asset-id "$asset" \
      >> "$LOG" 2>&1
  local rc=$?
  local t1=$(date +%s)
  local verdict="MISSING"
  if [ -f "$dir/metadata.json" ]; then
    verdict=$("$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('$dir/metadata.json')); v=m.get('validation',{})
n=len(json.load(open('$dir/trajectory.json')).get('trajectory',[]))
print(('PASS' if v.get('valid') else 'FAIL')+' frames='+str(n)+' '+str(list(v.get('reasons',[]))))" 2>/dev/null)
  fi
  printf "T1 %-16s %-46s rc=%d %4ds  %s\n" "$scen" "$asset" "$rc" "$((t1-t0))" "$verdict"
}

echo "=== motion #1 rolling ==="
run_one rolling 1001 gso_whey_protein_vanilla          rolling_gso
run_one rolling 1002 gso_room_essentials_fabric_cube_lavender rolling_gso
run_one rolling 1003 gso_ecoforms_plant_container_gp16a_coral rolling_gso

echo "=== motion #2 constant_force ==="
run_one constant_force 2001 gso_room_essentials_fabric_cube_lavender constant_force_gso
run_one constant_force 2002 gso_whey_protein_vanilla          constant_force_gso
run_one constant_force 2003 gso_ecoforms_plant_container_gp16a_coral constant_force_gso

echo "=== motion #3 free_fall ==="
run_one free_fall 3001 gso_down_to_earth_orchid_pot_ceramic_lime free_fall_gso
run_one free_fall 3002 gso_ecoforms_plant_container_gp16a_coral  free_fall_gso
run_one free_fall 3003 gso_mad_gab_refresh_card_game            free_fall_gso

echo "=== T1 DONE ==="
