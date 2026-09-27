#!/usr/bin/env bash
# Show the FULL traceback from the turntable probe.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
bash "$WS/tools/test_turntable_physics.sh" > "$WS/log/tt.log" 2>&1
echo "exit=$?"
echo "--- full tail ---"
tail -24 "$WS/log/tt.log" | sed 's/^/  /'
