#!/bin/bash
set -eu
umask 022
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node11
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v62/prepare_shared_inputs.py > /data/raw/huzijian/project1_database/log/V6.2_execution/shared_inputs.log 2>&1
