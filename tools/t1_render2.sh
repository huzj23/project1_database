#!/usr/bin/env bash
# ===========================================================================
# T1 PRODUCTION RENDER, v2 — all 14 clips, pre-validated through the CAMERA.
#
# preflight_full3.sh: 14/14 PASS (physics + camera).  The earlier run died on
# rolling clips 2 and 3 because my preflight omitted the camera step; that gap is
# closed, so no render time should now be lost to a framing rejection.
#
# Clip 1 (rolling / whey_protein_vanilla) already completed successfully
# (81 rgb + 81 depth + 81 seg + video.mp4, valid=True) and is SKIPPED here.
#
# The runner rewrites server.yaml's project.scenario_config between clips and
# calls generate.py WITHOUT --scenario (see diag_scenario.sh for why).
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
LOG="$WS/tmp/t1_render2.log"
: > "$LOG"

set_scenario () {
  sed -i "s|^  scenario_config: .*|  scenario_config: configs/scenarios/$1.yaml|" configs/server.yaml
}

run_one () {
  local scen="$1" seed="$2" asset="$3" cfg="$4"
  local padded
  padded=$(printf "seed-%06d" "$seed")
  local dir="datasets/$scen/$padded/x1"
  # skip if a complete sample already exists
  if [ -f "$dir/video.mp4" ] && [ "$(ls "$dir/rgb" 2>/dev/null | wc -l)" -ge 81 ]; then
    printf "T1 %-15s %-40s SKIP (already complete)\n" "$scen" "${asset#gso_}"
    return
  fi
  set_scenario "$cfg"
  rm -rf "datasets/$scen/$padded"
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
print(('PASS' if v.get('valid') else 'FAIL')+' '+str(list(v.get('reasons',[]))))" 2>/dev/null)
  fi
  local nframes=0
  [ -d "$dir/rgb" ] && nframes=$(ls "$dir/rgb" 2>/dev/null | wc -l)
  printf "T1 %-15s %-40s rc=%d %5ds rgb=%d %s\n" \
      "$scen" "${asset#gso_}" "$rc" "$((t1-t0))" "$nframes" "$verdict"
}

echo "=== motion #1 rolling (匀速) ==="
run_one rolling 1001 gso_whey_protein_vanilla                  rolling_gso
run_one rolling 1002 gso_room_essentials_fabric_cube_lavender  rolling_gso
run_one rolling 1003 gso_ecoforms_plant_container_gp16a_coral  rolling_gso

echo "=== motion #2 constant_force (匀加速) ==="
run_one constant_force 2001 gso_room_essentials_fabric_cube_lavender constant_force_gso
run_one constant_force 2002 gso_whey_protein_vanilla                  constant_force_gso
run_one constant_force 2003 gso_ecoforms_plant_container_gp16a_coral constant_force_gso

echo "=== motion #3 free_fall (自由落体) ==="
run_one free_fall 3001 gso_down_to_earth_orchid_pot_ceramic_lime free_fall_gso
run_one free_fall 3002 gso_ecoforms_plant_container_gp16a_coral  free_fall_gso
run_one free_fall 3003 gso_mad_gab_refresh_card_game             free_fall_gso

echo "=== motion #7 damping (阻尼) ==="
run_one damping 7001 gso_whey_protein_vanilla                  damping_gso
run_one damping 7002 gso_room_essentials_fabric_cube_lavender  damping_gso

echo "=== motion #4 projectile (抛体) ==="
run_one free_fall 4001 gso_mad_gab_refresh_card_game             projectile_gso
run_one free_fall 4002 gso_ecoforms_plant_container_gp16a_coral  projectile_gso
run_one free_fall 4003 gso_down_to_earth_orchid_pot_ceramic_lime projectile_gso

echo "=== T1 RENDER v2 DONE ==="
