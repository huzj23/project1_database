#!/usr/bin/env bash
# Re-run the jobs whose shard died.  Shard 5 crashed at launch (Blender wrote a
# crash dump 1 minute in), so its six `rotation ... _ay_` clips never rendered.
# Targeted re-run via --only rather than another full shard sweep.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
OUT="$WS/outcomes/dataset_real"
SESSION="phyco_requeue"

# which jobs are missing right now?
have=$(find "$OUT" -name sample.json 2>/dev/null | wc -l)
echo "already finished: $have / 36"

tmux kill-session -t "$SESSION" 2>/dev/null
tmux new-session -d -s "$SESSION" \
  "$BL --background --factory-startup --python $WS/code/scenarios/make_local_samples.py -- \
     --preset server_a --only _ay_ --frames 96 --samples 24 --resolution 1280x720 \
     --outcomes $OUT > $WS/log/requeue_ay.log 2>&1; echo DONE >> $WS/log/requeue_ay.log"

sleep 15
echo "requeued: rotation *_ay_* clips"
tail -2 "$WS/log/requeue_ay.log" 2>/dev/null | cut -c1-120
