#!/bin/bash
set -eu
ulimit -c 0
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node11
export XDG_CACHE_HOME=/data/raw/huzijian/project1_database/tmp/v62_node11/cache
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
export CUDA_VISIBLE_DEVICES=""
/data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v62/prepare_compat_runtime_r2.py > /data/raw/huzijian/project1_database/log/V6.2_execution/compat_runtime_r2.log 2>&1
