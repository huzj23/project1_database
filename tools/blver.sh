#!/usr/bin/env bash
# Blender version on the server + locate the binary.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
echo "  WS=$WS"
echo "  BLENDER=$BLENDER"
ls -la "$WS/tools/runtime/" 2>/dev/null | sed 's/^/  /'
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --version 2>&1 | head -3 | sed 's/^/  /'
