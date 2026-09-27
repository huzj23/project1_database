#!/usr/bin/env bash
# Run the wood turntable render, logging everything so the outcome is readable
# even when the remote shell swallows stdout.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i 's/\r$//' turntable_wood.sh
bash turntable_wood.sh > "$WS/log/tw.log" 2>&1
echo "exit=$?"
grep -E '^TW|Error|Traceback|line [0-9]+' "$WS/log/tw.log" | tail -20 | sed 's/^/  /'
