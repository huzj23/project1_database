#!/bin/bash
# Which frames are still missing, and is the render still moving?
R=/data/raw/huzijian/project1_database
F=$R/outcomes/v65/radio_scurve_domino/v65_20261007_final/frames
echo "=== watcher ==="
tail -6 "$R/log/V6.4_execution/v65_watch5.log" 2>/dev/null
n=$(ls "$F"/Scene_*.png 2>/dev/null | wc -l)
echo "=== frames: $n/216 ==="
missing=""
for i in $(seq 1 216); do
  f=$(printf '%s/Scene_%05d.png' "$F" "$i")
  [ -f "$f" ] || missing="$missing $i"
done
echo "missing:$missing"
echo "=== workers alive ==="
/usr/bin/tmux -S "$R/tmp/v64_node12_control.sock" ls 2>/dev/null | grep -c 'v65_rnd_'
date '+%H:%M:%S'
