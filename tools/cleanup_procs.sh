#!/usr/bin/env bash
# Kill leftover PhyCo-Sim processes (only ones belonging to THIS workspace).
# Matching is anchored on the workspace path so no other user's job is touched.
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "--- before ---"
ps -eo pid,etime,cmd 2>/dev/null |
  grep -E "[c]onda_env/bin/python|$WS/code/scenarios" | head -10

# collect pids whose command line references our workspace
pids=$(ps -eo pid,cmd 2>/dev/null |
       awk -v ws="$WS" 'index($0, ws) > 0 && index($0, "python") > 0 {print $1}')

if [ -n "$pids" ]; then
  echo "--- terminating: $pids"
  kill $pids 2>/dev/null
  sleep 3
  still=$(ps -eo pid,cmd 2>/dev/null |
          awk -v ws="$WS" 'index($0, ws) > 0 && index($0, "python") > 0 {print $1}')
  if [ -n "$still" ]; then
    echo "--- force killing: $still"
    kill -9 $still 2>/dev/null
    sleep 2
  fi
else
  echo "--- nothing to kill"
fi

echo "--- after ---"
n=$(ps -eo cmd 2>/dev/null | awk -v ws="$WS" 'index($0, ws) > 0 && index($0, "python") > 0' | wc -l)
echo "  remaining: $n"

echo "--- scratch cleanup ---"
rm -rf "$WS/tmp"/phyco_scratch_* 2>/dev/null
echo "  tmp size: $(du -sh "$WS/tmp" 2>/dev/null | cut -f1)"
