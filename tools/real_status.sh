#!/usr/bin/env bash
# Progress report for the "A" main track (GSO actors on the warehouse HDRI set).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
OUT="$WS/outcomes/dataset_real"

echo "================= real batch $(date '+%F %T') ================="
echo "clips finished : $(find "$OUT" -name sample.json 2>/dev/null | wc -l) / 36"
echo "running procs  : $(ps -eo cmd 2>/dev/null | grep -c '[m]ake_local_samples')"
if [ -d "$OUT" ]; then
  echo "size           : $(du -sh "$OUT" 2>/dev/null | cut -f1)"
fi

echo
echo "--- per shard ---"
for i in 0 1 2 3 4 5; do
  f="$WS/log/real_shard$i.log"
  [ -f "$f" ] || { printf '  s%s: (no log)\n' "$i"; continue; }
  done_n=$(grep -c '^\[sample\] .*d=' "$f" 2>/dev/null)
  last=$(grep '^\[sample\] .*d=' "$f" 2>/dev/null | tail -1)
  t=$(grep -oE 'Time:[0-9:]+' "$f" 2>/dev/null | tail -1)
  printf '  s%s: %2s done | %s | %s\n' "$i" "$done_n" "${last:0:70}" "$t"
done

echo
echo "--- finished clips ---"
if [ -d "$OUT" ]; then
  for d in "$OUT"/*/; do
    [ -f "$d/sample.json" ] || continue
    n=$(basename "$d")
    sz=$(du -sh "$d" 2>/dev/null | cut -f1)
    printf '  %-46s %s\n' "$n" "$sz"
  done
fi

echo
echo "--- node load ---"
uptime | sed 's/^/  /'
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null | sed 's/^/  gpu /'
echo "============================================================="
