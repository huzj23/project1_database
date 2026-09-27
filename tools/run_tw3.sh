#!/usr/bin/env bash
# Render the wood turntable on the indoor table, capture diagnostics, keep output.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i 's/\r$//' tt_wood_table.sh
bash tt_wood_table.sh > "$WS/log/tw2.log" 2>&1
echo "exit=$?"
echo "=== diagnostics ==="
grep -E '^TW' "$WS/log/tw2.log" | sed 's/^/  /'
echo "=== output files ==="
ls -la "$WS/outcomes/_turntable_wood" | sed 's/^/  /'
