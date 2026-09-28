#!/usr/bin/env bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"
export OMP_NUM_THREADS="8"
export OPENBLAS_NUM_THREADS="8"
export MKL_NUM_THREADS="8"
export TMPDIR="/data/raw/huzijian/project1_database/tmp"
export TEMP="/data/raw/huzijian/project1_database/tmp"
export TMP="/data/raw/huzijian/project1_database/tmp"

/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender \
  --background \
  --factory-startup \
  --threads 8 \
  --python /data/raw/huzijian/project1_database/tools/v5_render_object_candidate_stills.py
