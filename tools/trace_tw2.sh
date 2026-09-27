#!/usr/bin/env bash
# Show the trace around where the wood-turntable script dies.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i '1s/^\xEF\xBB\xBF//; s/\r$//' turntable_wood.sh
bash -x turntable_wood.sh > "$WS/log/twxtrace.log" 2>&1
echo "exit=$?"
echo "=== trace tail ==="
tail -30 "$WS/log/twxtrace.log" | sed 's/^/  /'
