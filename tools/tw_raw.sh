#!/usr/bin/env bash
# Capture the RAW python output from the wood-turntable run.  The earlier wrapper
# piped through `grep -E '^TW|^  '`, which discarded the actual traceback.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i '1s/^\xEF\xBB\xBF//; s/\r$//' turntable_wood.sh
bash turntable_wood.sh > "$WS/log/twraw.log" 2>&1
echo "exit=$?  bytes=$(wc -c < "$WS/log/twraw.log")"
echo "=== raw tail ==="
tail -25 "$WS/log/twraw.log" | sed 's/^/  /'
