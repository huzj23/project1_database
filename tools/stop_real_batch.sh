#!/usr/bin/env bash
# Stop the real-track batch and clean its scratch/output, leaving the workspace tidy.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

for i in 0 1 2 3 4 5; do
  tmux kill-session -t "phyco_real_$i" 2>/dev/null
done
sleep 3

# stop only our own render processes (no self-match: the bracket trick)
for p in $(ps -eo pid,cmd | awk -v ws="$WS" 'index($0,ws)>0 && index($0,"make_local_samples")>0 {print $1}'); do
  kill "$p" 2>/dev/null
done
sleep 3

left=$(ps -eo cmd | grep -c '[m]ake_local_samples')
echo "remaining render procs: $left"

if [ "${1:-}" = "--clean" ]; then
  rm -rf "$WS/outcomes/dataset_real"
  rm -rf "$WS/tmp"/ls_* "$WS/tmp"/phyco_scratch_* 2>/dev/null
  echo "cleaned dataset_real and scratch"
fi

tmux ls 2>/dev/null | grep '^phyco_' || echo "no phyco tmux sessions left"
