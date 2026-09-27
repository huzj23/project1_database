#!/usr/bin/env bash
# Run the turntable physics sweep (kept in a script so the BOM/encoding problems
# from an inlined PowerShell edit cannot recur).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i 's/\r$//; 1s/^\xEF\xBB\xBF//' tt_physics.sh
bash tt_physics.sh 2>&1 | grep -E '^TT|Error|Traceback|line ' | tail -16
