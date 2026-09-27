#!/usr/bin/env bash
# Download the final mahogany turntable frames and verify the disc colour/grain.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
echo "remote files:"
ls -la "$WS/outcomes/_tt_final" | sed 's/^/  /'
ls -la "$WS/outcomes/_tt_wood_variants" | sed 's/^/  /'
