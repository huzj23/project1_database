#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v63_node12
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=16
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/launch_gpu_stills_r1.py > /data/raw/huzijian/project1_database/tmp/v63_node12/gpu_static_control_r1.log 2>&1
