#!/usr/bin/env bash
# Framing probe: set up every job's scene and report the subject's share of the
# frame WITHOUT rendering.  36 renders would cost ~2 h; this costs a few minutes
# and catches framing regressions before committing the batch.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
SHARDS="${1:-6}"
FRAMES="${2:-96}"

OUT="$WS/outcomes/_framing_probe"
rm -rf "$OUT"; mkdir -p "$OUT"

for i in $(seq 0 $((SHARDS - 1))); do
  tmux kill-session -t "probe_$i" 2>/dev/null
  tmux new-session -d -s "probe_$i" \
    "$BL --background --factory-startup --python $WS/code/scenarios/make_local_samples.py -- \
       --preset server_a --probe_only --shard_index $i --shard_total $SHARDS \
       --frames $FRAMES --outcomes $OUT > $WS/log/probe_$i.log 2>&1; echo DONE >> $WS/log/probe_$i.log"
done

echo "waiting for $SHARDS probe shards..."
for _ in $(seq 1 120); do
  n=$(ps -eo cmd | grep -c '[m]ake_local_samples')
  [ "$n" -eq 0 ] && break
  sleep 10
done

echo
printf '%-46s %7s %8s %8s %8s\n' "job" "cam_d" "actor%" "traj_m" "traj/obj"
printf '%-46s %7s %8s %8s %8s\n' "----------------------------------------------" "-----" "------" "------" "------"
grep -h 'actor=' "$WS"/log/probe_*.log 2>/dev/null |
  sed -E 's/.*\[sample\] ([^:]+): d=([0-9.]+)m actor=([0-9]+)%.*/\1 \2 \3/' |
  sort | while read -r tag d a; do
    printf '%-46s %7s %8s\n' "$tag" "$d" "$a"
  done

echo
echo "shards still running: $(ps -eo cmd | grep -c '[m]ake_local_samples')"
echo "actor%% summary:"
grep -h -o 'actor=[0-9]*%' "$WS"/log/probe_*.log 2>/dev/null |
  grep -o '[0-9]*' | sort -n | awk '
    {v[NR]=$1; s+=$1}
    END {if (NR==0) {print "  (no data)"; exit}
         printf "  n=%d  min=%d  median=%d  max=%d  mean=%.1f\n",
                NR, v[1], v[int((NR+1)/2)], v[NR], s/NR}'
