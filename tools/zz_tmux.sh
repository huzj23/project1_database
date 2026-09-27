#!/usr/bin/env bash
# Usage: bash zz_tmux.sh <session> <script.sh>
S="$1"; SC="$2"
tmux new-session -d -s "$S" "bash $SC > /data/raw/huzijian/project1_database/tmp/$S.log 2>&1"
sleep 2
tmux ls
