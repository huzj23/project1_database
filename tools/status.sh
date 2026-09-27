#!/usr/bin/env bash
# One-shot status report for the PhyCo-Sim work on this server.
# Read-only: prints paths, logs, session state and output inventory.
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "================= PhyCo-Sim status  $(date '+%F %T') ================="

echo
echo "--- my tmux sessions ---"
tmux ls 2>/dev/null | grep -E '^(phyco_[a-z_]+):' || echo "  (none running)"

echo
echo "--- newest batch log ---"
NEW=$(ls -t "$WS"/log/batch_*.log 2>/dev/null | head -1)
if [ -n "$NEW" ]; then
  echo "  $NEW"
  tail -25 "$NEW" | sed 's/^/  | /'
else
  echo "  (no batch logs yet)"
fi

echo
echo "--- output inventory ---"
OUT="$WS/outcomes/dataset/single_object"
if [ -d "$OUT" ]; then
  done=$(find "$OUT" -name metadata.json 2>/dev/null | wc -l)
  dirs=$(find "$OUT" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
  echo "  complete videos : $done"
  echo "  output dirs     : $dirs"
  du -sh "$OUT" 2>/dev/null | sed 's/^/  size: /'
  echo "  newest:"
  ls -t "$OUT" 2>/dev/null | head -5 | sed 's/^/    /'
else
  echo "  (no output yet)"
fi

echo
echo "--- disk ---"
df -h "$WS" 2>/dev/null | tail -2 | sed 's/^/  /'
du -sh "$WS/tools/conda_env" "$WS/outcomes" "$WS/tmp" 2>/dev/null | sed 's/^/  /'

echo
echo "--- crashes reported in newest log (if any) ---"
if [ -n "$NEW" ]; then
  grep -cE 'Segmentation fault|Fatal Python error' "$NEW" 2>/dev/null | sed 's/^/  count: /'
fi
echo "====================================================================="
