#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v63_node11
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export CUDA_VISIBLE_DEVICES=-1
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/layout_ground_r3.py > /data/raw/huzijian/project1_database/tmp/v63_node11/layout_r3.log 2>&1
