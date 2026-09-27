#!/usr/bin/env bash
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/code/physics-video-sim/physics-video-sim-main" || exit 1
"$WS/tools/conda_env/bin/python" "$WS/tools/zz_final.py" 2>&1
