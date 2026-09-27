#!/usr/bin/env bash
# Final preflight, post-change.
source /data/raw/huzijian/project1_database/tools/server_env.sh
bash "$WS/tools/preflight_full3.sh" > "$WS/tmp/zz_preflight_final.log" 2>&1
echo "EXIT=$?" >> "$WS/tmp/zz_preflight_final.log"
