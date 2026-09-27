#!/usr/bin/env bash
# Are my simulation processes still alive, and what are they doing?
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "--- my python processes (conda env) ---"
ps -eo pid,etime,pcpu,rss,cmd 2>/dev/null | grep '[c]onda_env/bin/python' | head -5 || echo "  (none)"

echo
echo "--- any run_single_object / generate_batch ---"
ps -eo pid,etime,pcpu,cmd 2>/dev/null | grep -E '[r]un_single_object|[g]enerate_batch' | head -5 || echo "  (none)"

echo
echo "--- scratch dirs in workspace tmp ---"
ls -1 "$WS/tmp" 2>/dev/null | head -10
echo "  count: $(ls -1 "$WS/tmp" 2>/dev/null | wc -l)"
du -sh "$WS/tmp" 2>/dev/null | sed 's/^/  /'

echo
echo "--- newest log, full tail ---"
NEW=$(ls -t "$WS"/log/batch_*.log 2>/dev/null | head -1)
echo "  file: $NEW"
tail -30 "$NEW" 2>/dev/null | sed 's/^/  | /'

echo
echo "--- per-job output dirs ---"
OUT="$WS/outcomes/dataset/single_object"
for d in "$OUT"/*/; do
  [ -d "$d" ] || continue
  n=$(ls -1 "$d" 2>/dev/null | wc -l)
  echo "  $(basename "$d"): $n files"
done
