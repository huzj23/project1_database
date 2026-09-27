#!/usr/bin/env bash
# Baseline preflight before any change.
source /data/raw/huzijian/project1_database/tools/server_env.sh
mkdir -p "$WS/tmp"
bash "$WS/tools/preflight_full3.sh" > "$WS/tmp/zz_preflight_baseline.log" 2>&1
echo "EXIT=$?" >> "$WS/tmp/zz_preflight_baseline.log"
