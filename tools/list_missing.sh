#!/usr/bin/env bash
# List which of the 36 expected jobs are finished and which are still missing.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
OUT="$WS/outcomes/dataset_real"

ACTORS="elephant roomessentialsfabr cardgame gp16acoral lime vanilla"
declare -a EXPECTED
for a in $ACTORS; do
  EXPECTED+=("circular_${a}_r075_p50" "circular_${a}_r110_p35"
             "damped_${a}_t25_k055"   "damped_${a}_t38_k085"
             "rotation_${a}_az_p40"   "rotation_${a}_ay_p30")
done

echo "=== finished ==="
nf=0
for t in "${EXPECTED[@]}"; do
  if [ -f "$OUT/$t/sample.json" ]; then
    printf '  OK   %s\n' "$t"; nf=$((nf+1))
  fi
done
echo "  -> $nf / ${#EXPECTED[@]}"

echo
echo "=== MISSING ==="
nm=0
for t in "${EXPECTED[@]}"; do
  if [ ! -f "$OUT/$t/sample.json" ]; then
    printf '  --   %s\n' "$t"; nm=$((nm+1))
  fi
done
echo "  -> $nm missing"

echo
echo "=== shard5 style filter matches ==="
echo "  _ay_ jobs present: $(find "$OUT" -name sample.json -path '*_ay_*' | wc -l) / 6"
