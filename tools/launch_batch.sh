#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Launch a PhyCo-Sim batch in a persistent tmux session.
#
# Usage:
#   bash tools/launch_batch.sh <preset> [workers]
#   LOOK=interior bash tools/launch_batch.sh interior 6
#
# Environment:
#   WORKERS  GPU  RES  SPP  LOOK  FRAME_FORMAT  MOTION_BLUR
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

PRESET="${1:-smoke}"
WORKERS="${2:-${WORKERS:-6}}"
SESSION="phyco_${PRESET}"

# tidy scratch so the workspace tmp dir does not grow unbounded
rm -rf "$WS/tmp"/phyco_scratch_* 2>/dev/null

tmux kill-session -t "$SESSION" 2>/dev/null
sleep 1

tmux new-session -d -s "$SESSION" \
  "WORKERS=$WORKERS GPU=${GPU:-0} RES=${RES:-1280x720} SPP=${SPP:-24} \
   LOOK=${LOOK:-studio} FRAME_FORMAT=${FRAME_FORMAT:-png} \
   MOTION_BLUR=${MOTION_BLUR:-0.25} \
   bash $WS/tools/run_server.sh $PRESET; \
   echo DONE > $WS/log/${PRESET}.done; exec bash"

sleep 10
{
  echo "launched $(date '+%F %T')  preset=$PRESET session=$SESSION workers=$WORKERS"
  echo "  look=${LOOK:-studio} res=${RES:-1280x720} spp=${SPP:-24} fmt=${FRAME_FORMAT:-png}"
  echo "  running jobs: $(ps -eo cmd 2>/dev/null | grep -c '[r]un_single_object')"
} | tee "$WS/log/${PRESET}_launch.txt"
