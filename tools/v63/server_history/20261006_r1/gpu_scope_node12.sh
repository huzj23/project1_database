#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v63_node12
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/gpu_scoped_launch.py > /data/raw/huzijian/project1_database/tmp/v63_node12/gpu_scope_probe_r1.log 2>&1
