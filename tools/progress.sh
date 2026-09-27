#!/usr/bin/env bash
# Live render progress: how many frames has each worker produced so far?
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== worker processes ==="
ps -eo pid,etime,pcpu,rss,cmd 2>/dev/null |
  grep '[r]un_single_object' |
  sed -E 's/.*--video_id ([^ ]+).*/  \1/' |
  while read -r line; do
    echo "$line"
  done | head -8

echo
echo "=== frames rendered per scratch dir ==="
total=0
for d in "$WS"/tmp/phyco_scratch_*; do
  [ -d "$d" ] || continue
  n=$(ls -1 "$d/exr" 2>/dev/null | wc -l)
  total=$((total + n))
  printf '  %-34s %3d frames\n' "$(basename "$d")" "$n"
done
echo "  total frames rendered so far: $total"

echo
echo "=== batch log tail ==="
NEW=$(ls -t "$WS"/log/batch_phase1_*.log 2>/dev/null | head -1)
grep -E '\[batch\] \[' "$NEW" 2>/dev/null | tail -5 | sed 's/^/  /'
echo "  completed: $(find "$WS/outcomes/dataset/single_object" -name metadata.json 2>/dev/null | wc -l) / 36"

echo
echo "=== elapsed ==="
echo "  started: $(head -3 "$NEW" 2>/dev/null | grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1)"
echo "  now    : $(date +%T)"
