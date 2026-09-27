#!/usr/bin/env bash
# ===========================================================================
# Launch the SINGLE 匀速 clip (motion #1) on camera C, then the 2 damping clips.
#
# Ordering rationale: the machine has 104 cores and Cycles is CPU-bound; the T3
# spin clip is still running, so this runner WAITS for it rather than doubling the
# load (two concurrent Cycles jobs each slow down, and a previous attempt at
# concurrent generate.py runs corrupted a shared cache directory).
#
# Clip budget: the user allowed "最多再跑一条" 匀速.  So rolling = 1 clip (seed 1001,
# the preflighted one).  Damping's 2 clips are a REPAIR of previously failed clips
# (they never rendered at all because `scenario: damping` was missing from every
# asset's allowed_scenarios), not new work.
#
# Everything is preflighted through the CAMERA step, because a framing rejection
# costs a full 20-minute render.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
LOG="$WS/tmp/t1c_render.log"
: > "$LOG"

set_scenario () {
  sed -i "s|^  scenario_config: .*|  scenario_config: configs/scenarios/$1.yaml|" configs/server.yaml
}

run_one () {
  local scen="$1" seed="$2" asset="$3" cfg="$4" tag="$5"
  local padded; padded=$(printf "seed-%06d" "$seed")
  local dir="datasets/$scen/$padded/x1"
  if [ -f "$dir/video.mp4" ] && [ "$(ls "$dir/rgb" 2>/dev/null | wc -l)" -ge 81 ]; then
    printf "%-14s %-34s %-4s SKIP (complete)\n" "$scen" "${asset#gso_}" "$tag"
    return
  fi
  set_scenario "$cfg"
  rm -rf "datasets/$scen/$padded"
  local t0=$(date +%s)
  "$WS/tools/conda_env/bin/python" scripts/generate.py \
      --config configs/server.yaml \
      --seed "$seed" --variant x1 --asset-id "$asset" >> "$LOG" 2>&1
  local rc=$?
  local t1=$(date +%s)
  local verdict="MISSING"
  if [ -f "$dir/metadata.json" ]; then
    verdict=$("$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('$dir/metadata.json')); v=m.get('validation',{})
print(('PASS' if v.get('valid') else 'FAIL')+' '+str(list(v.get('reasons',[]))))" 2>/dev/null)
  fi
  local n=0; [ -d "$dir/rgb" ] && n=$(ls "$dir/rgb" 2>/dev/null | wc -l)
  printf "%-14s %-34s %-4s rc=%d %5ds rgb=%d %s\n" \
      "$scen" "${asset#gso_}" "$tag" "$rc" "$((t1-t0))" "$n" "$verdict"
}

echo "=== waiting for any running generate.py to finish first ==="
for i in $(seq 1 240); do
  if ! pgrep -f 'generate.py' > /dev/null; then echo "  machine free after ${i}0s"; break; fi
  sleep 10
done
pgrep -af generate.py | sed 's/^/  still running: /' || echo "  clear"

echo
echo "=== motion #1 匀速  (camera C, whey can rolling on its side) ==="
run_one rolling 1001 gso_whey_protein_vanilla rolling_gso camC

echo
echo "=== motion #7 阻尼  (repair of the 2 clips that never rendered) ==="
run_one damping 7001 gso_whey_protein_vanilla damping_gso d1
run_one damping 7002 gso_whey_protein_vanilla damping_gso d2

echo
echo "=== DONE ==="
date
