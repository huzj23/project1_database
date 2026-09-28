#!/usr/bin/env bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"
export OMP_NUM_THREADS="8"

/data/raw/huzijian/project1_database/tools/conda_env/bin/python \
  /data/raw/huzijian/project1_database/tools/v5_inspect_scene_archives.py
