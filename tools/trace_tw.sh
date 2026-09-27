#!/usr/bin/env bash
# Trace the wood-turntable script to find why it dies before producing output.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i '1s/^\xEF\xBB\xBF//; s/\r$//' turntable_wood.sh
echo "=== trace (first 40 lines of xtrace) ==="
bash -x turntable_wood.sh 2>&1 | head -40 | sed 's/^/  /'
