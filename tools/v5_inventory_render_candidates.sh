#!/usr/bin/env bash
set -euo pipefail

export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"
export OMP_NUM_THREADS="8"
export OPENBLAS_NUM_THREADS="8"
export MKL_NUM_THREADS="8"

/usr/bin/nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader
/data/raw/huzijian/project1_database/tools/conda_env/bin/python \
  /data/raw/huzijian/project1_database/tools/v5_inventory_render_candidates.py
