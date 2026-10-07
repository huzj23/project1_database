#!/bin/bash
# Report each r3 worker's status: is it alive, and did its launcher accept the GPU?
R=/data/raw/huzijian/project1_database
for w in w1 w2 w3 w4 w5 w6; do
  name="v65_rnd_${w}_r3"
  alive=$(/usr/bin/tmux -S "$R/tmp/v64_node12_control.sock" has-session -t "$name" 2>/dev/null && echo ALIVE || echo GONE)
  printf '%-16s %-6s ' "$name" "$alive"
  tail -3 "$R/log/V6.4_execution/${name}.log" 2>/dev/null | tr '\n' '|' | cut -c1-150
  echo
done
echo "--- frames on disk ---"
ls "$R/outcomes/v65/radio_scurve_domino/v65_20261007_final/frames/"*.png 2>/dev/null | wc -l
echo "--- gpu ---"
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
