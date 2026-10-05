#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
/usr/bin/mkdir -p /data/raw/huzijian/project1_database/tmp/v63_node11
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v63_node11
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/resource_probe.py /data/raw/huzijian/project1_database/tmp/v63_node11/resources_initial.json > /data/raw/huzijian/project1_database/tmp/v63_node11/resources_initial.log 2>&1
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/prepare_inputs.py > /data/raw/huzijian/project1_database/tmp/v63_node11/prepare_inputs.log 2>&1
