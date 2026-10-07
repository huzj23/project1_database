#!/bin/bash
# Measure what the render is actually limited by, so the ETA is based on the machine rather than on a guess.
R=/data/raw/huzijian/project1_database
echo "=== CPUs ==="
nproc
echo "=== load ==="
uptime
echo "=== my blender processes: pid, threads, %cpu, elapsed ==="
for p in $(pgrep -u "$(whoami)" -f 'blender' 2>/dev/null); do
  th=$(ls /proc/$p/task 2>/dev/null | wc -l)
  # %cpu from ps is an average over the process lifetime; read the instantaneous value instead
  cpu=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null)
  et=$(ps -o etime= -p $p 2>/dev/null | tr -d ' ')
  printf '  pid=%-7s threads=%-4s utime+stime=%-10s elapsed=%s\n' "$p" "$th" "$cpu" "$et"
done
echo "=== instantaneous cpu% (top 8) ==="
top -bn1 | head -14 | tail -9
echo "=== gpu util ==="
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
echo "=== memory ==="
free -g | sed -n '2p'
echo "=== frames done ==="
ls "$R/outcomes/v65/radio_scurve_domino/v65_20261007_final/frames/"*.png 2>/dev/null | wc -l
date '+%H:%M:%S'
