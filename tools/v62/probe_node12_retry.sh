#!/bin/bash
set -eu
umask 002
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node12
export TEMP=/data/raw/huzijian/project1_database/tmp/v62_node12
export TMP=/data/raw/huzijian/project1_database/tmp/v62_node12
export XDG_CACHE_HOME=/data/raw/huzijian/project1_database/tmp/v62_node12/cache
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH=/data/raw/huzijian/project1_database/tools/runtime/lib
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
/data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v62/server_probe_v2.py node12 /data/raw/huzijian/project1_database/tmp/v62_node12/probe.json > /data/raw/huzijian/project1_database/tmp/v62_node12/probe.log 2>&1
