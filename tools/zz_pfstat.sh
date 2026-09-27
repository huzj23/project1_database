#!/usr/bin/env bash
echo "--- preflight final log ---"
cat /data/raw/huzijian/project1_database/tmp/zz_preflight_final.log 2>&1
echo "--- tmux session state ---"
tmux has-session -t zz_preflight_final 2>/dev/null && echo STILL_RUNNING || echo DONE
