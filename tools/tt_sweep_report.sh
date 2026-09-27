#!/usr/bin/env bash
# Run the turntable physics sweep and show the result table.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
bash "$WS/tools/test_turntable_physics.sh" > "$WS/log/ttsweep.log" 2>&1
echo "exit=$?"
echo "--- result ---"
grep -E '^TT|Error|Traceback|line [0-9]+' "$WS/log/ttsweep.log" | tail -22 | sed 's/^/  /'
