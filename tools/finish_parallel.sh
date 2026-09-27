#!/usr/bin/env bash
# Finish the batch in parallel: one Blender process per missing job.
#
# The first requeue ran the 7 gaps sequentially inside a single tmux session,
# which at ~25 min/clip means ~2 h for the remainder.  One process per job turns
# that into a single ~25 min pass.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
OUT="$WS/outcomes/dataset_real"

# stop the sequential requeue
tmux kill-session -t phyco_requeue 2>/dev/null
sleep 2
for p in $(ps -eo pid,cmd | awk -v ws="$WS" 'index($0,ws)>0 && index($0,"make_local_samples")>0 {print $1}'); do
  kill "$p" 2>/dev/null
done
sleep 3

# figure out what is still missing
ACTORS="elephant roomessentialsfabr cardgame gp16acoral lime vanilla"
MISSING=()
for a in $ACTORS; do
  for t in "circular_${a}_r075_p50" "circular_${a}_r110_p35" \
           "damped_${a}_t25_k055"   "damped_${a}_t38_k085" \
           "rotation_${a}_az_p40"   "rotation_${a}_ay_p30"; do
    [ -f "$OUT/$t/sample.json" ] || MISSING+=("$t")
  done
done

echo "missing: ${#MISSING[@]}"
if [ "${#MISSING[@]}" -eq 0 ]; then echo "nothing to do"; exit 0; fi

i=0
for tag in "${MISSING[@]}"; do
  s="fix_$i"
  tmux kill-session -t "$s" 2>/dev/null
  tmux new-session -d -s "$s" \
    "$BL --background --factory-startup --python $WS/code/scenarios/make_local_samples.py -- \
       --preset server_a --only $tag --frames 96 --samples 24 --resolution 1280x720 \
       --outcomes $OUT > $WS/log/fix_$i.log 2>&1; echo DONE >> $WS/log/fix_$i.log"
  printf '  -> %-40s tmux %s\n' "$tag" "$s"
  i=$((i + 1))
done

sleep 20
echo
echo "running procs: $(ps -eo cmd | grep -c '[m]ake_local_samples')"
