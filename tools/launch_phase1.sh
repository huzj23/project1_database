#!/usr/bin/env bash
# Launch the phase-1 delivery batch (36 videos) in a persistent tmux session.
#
# 12 circular + 12 damped + 12 rotation, 768x432, 64 spp, 96 frames, HDRI light.
# CPU rendering on purpose (see run_server.sh for why GPU is not used).
source /data/raw/huzijian/project1_database/tools/server_env.sh

SESSION="phyco_phase1"
JOBS_LOG="$WS/log/phase1_launch.txt"

# tidy previous scratch so the workspace tmp dir does not grow unbounded
rm -rf "$WS/tmp"/phyco_scratch_* "$WS/tmp"/HDRI_haven* 2>/dev/null

tmux kill-session -t "$SESSION" 2>/dev/null
sleep 1

tmux new-session -d -s "$SESSION" \
  "WORKERS=${WORKERS:-8} GPU=${GPU:-0} bash $WS/tools/run_server.sh phase1; echo DONE > $WS/log/phase1.done; exec bash"

sleep 8
{
  echo "launched $(date '+%F %T')  session=$SESSION  workers=${WORKERS:-8}"
  echo "--- sessions ---"
  tmux ls 2>/dev/null | grep phyco || echo "  (none)"
  echo "--- running jobs ---"
  ps -eo pid,etime,pcpu,cmd 2>/dev/null | grep '[r]un_single_object' | wc -l
} | tee "$JOBS_LOG"
