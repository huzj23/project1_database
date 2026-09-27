#!/usr/bin/env bash
# Compliance self-check: confirm the work stayed inside the designated workspace.
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== 1. conda user-state was redirected into the workspace ==="
for p in "$WS/tools/home/.conda" "$WS/tools/home/.condarc" "$WS/tools/condarc"; do
  if [ -e "$p" ]; then echo "  present: $p"; else echo "  absent : $p"; fi
done
ls -la "$WS/tools/home" 2>/dev/null | head -8 | sed 's/^/    /'

echo
echo "=== 2. TMPDIR points inside the workspace ==="
echo "  TMPDIR=$TMPDIR"
python3 -c "import tempfile;print('  python tempfile ->', tempfile.gettempdir())" 2>/dev/null

echo
echo "=== 3. scratch directories created by this project ==="
find "$WS/tmp" -maxdepth 1 -name 'phyco_scratch_*' 2>/dev/null | wc -l | sed 's/^/  count: /'

echo
echo "=== 4. all outputs live under the workspace ==="
du -sh "$WS/outcomes" 2>/dev/null | sed 's/^/  /'

echo
echo "=== 5. workspace footprint ==="
du -sh "$WS" 2>/dev/null | sed 's/^/  total: /'
for d in code models outcomes log tmp tools; do
  du -sh "$WS/$d" 2>/dev/null | sed 's/^/  /'
done

echo
echo "=== 6. batch progress ==="
OUT="$WS/outcomes/dataset/single_object"
echo "  complete: $(find "$OUT" -name metadata.json 2>/dev/null | wc -l) / 36"
NEW=$(ls -t "$WS"/log/batch_phase1_*.log 2>/dev/null | head -1)
grep -cE 'FAIL' "$NEW" 2>/dev/null | sed 's/^/  FAIL lines: /'
grep -E '^\| \[batch\] \[[0-9]+/36\]' "$NEW" 2>/dev/null | tail -4 | sed 's/^/  /'
grep -oE '[0-9]+/36 ok' "$NEW" 2>/dev/null | tail -1 | sed 's/^/  summary: /'
