#!/bin/bash
set -eu
umask 022
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node11
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
/data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v62/mechanism_probe.py > /data/raw/huzijian/project1_database/log/V6.2_execution/mechanism_probe.log 2>&1
