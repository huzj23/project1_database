#!/usr/bin/env bash
# ===========================================================================
# Render the 4 RED-WOOD turntable clips at the pulled-back camera (k=1.5).
#
# Preflight (preflight_tt4.sh): all four valid=True, arc +345..+351 deg, orbit
# radius constant, projected max |norm| 0.40-0.60 (well inside the frame).
#
# Each clip needs its own server config, so the runner rewrites the config's
# project.scenario_config and calls generate.py WITHOUT --scenario (adding
# --scenario would replace scenario_config with the mentor's default and pick
# absent maps).
#
# The old clips are ARCHIVED first, not deleted, so before/after (grey vs red wood,
# near vs pulled-back) stays comparable.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
LOG="$WS/tmp/tt_wood_render.log"
: > "$LOG"
ARCH="$WS/tmp/tt_grey_near_camera"
mkdir -p "$ARCH"

run_one () {
  local scen="$1" seed="$2" cfg="$3"
  local padded; padded=$(printf "seed-%06d" "$seed")
  local dir="datasets/$scen/$padded"
  # archive the previous (grey, near-camera) version rather than deleting it
  if [ -d "$dir" ]; then
    rm -rf "$ARCH/$scen-$padded"
    mv "$dir" "$ARCH/$scen-$padded"
    echo "  archived old $dir -> $ARCH/$scen-$padded"
  fi
  sed -i "s|^  scenario_config: .*|  scenario_config: configs/scenarios/$cfg.yaml|" configs/server.yaml
  local t0=$(date +%s)
  "$WS/tools/conda_env/bin/python" scripts/generate.py \
      --config "configs/server_$scen.yaml" \
      --seed "$seed" --variant x1 --asset-id gso_sootheze_cold_therapy_elephant >> "$LOG" 2>&1
  local rc=$?; local t1=$(date +%s)
  local d="$dir/x1"
  local verdict="MISSING"
  if [ -f "$d/metadata.json" ]; then
    verdict=$("$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('$d/metadata.json')); v=m.get('validation',{})
print(('PASS' if v.get('valid') else 'FAIL')+' '+str(list(v.get('reasons',[]))))" 2>/dev/null)
  fi
  printf "TT %-16s %d rc=%d %5ds rgb=%d %s\n" "$scen" "$seed" "$rc" "$((t1-t0))" \
      "$(ls $d/rgb 2>/dev/null | wc -l)" "$verdict"
}

echo "=== #5 环形转动 (turntable_carry) ==="
run_one turntable_carry 5001 turntable_carry_gso
run_one turntable_carry 5002 turntable_carry_gso
echo "=== #6 转盘上的转动 (turntable_spin) ==="
run_one turntable_spin 5001 turntable_spin_gso
run_one turntable_spin 5002 turntable_spin_gso
echo "=== DONE ==="
date
