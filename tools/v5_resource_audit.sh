#!/bin/bash
set -u

WORKSPACE=/data/raw/huzijian/project1_database

/usr/bin/printf '%s\n' '=== timestamp ==='
/usr/bin/date -Is
/usr/bin/printf '%s\n' '=== host ==='
/usr/bin/hostname
/usr/bin/printf '%s\n' '=== gpu summary ==='
/usr/bin/nvidia-smi \
  --query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader
/usr/bin/printf '%s\n' '=== gpu compute processes ==='
/usr/bin/nvidia-smi \
  --query-compute-apps=gpu_uuid,pid,process_name,used_memory \
  --format=csv,noheader
/usr/bin/printf '%s\n' '=== tmux sessions ==='
/usr/bin/tmux list-sessions | /usr/bin/wc -l
/usr/bin/tmux list-sessions | /usr/bin/grep '^p1_v5_' || /usr/bin/true
/usr/bin/printf '%s\n' '=== project top-level entries ==='
/usr/bin/find "$WORKSPACE" -mindepth 1 -maxdepth 1 -printf '%y %p\n' | /usr/bin/sort
/usr/bin/printf '%s\n' '=== project filesystem ==='
/usr/bin/df -h "$WORKSPACE"
/usr/bin/printf '%s\n' 'AUDIT_DONE'

exec /bin/bash
