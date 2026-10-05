#!/bin/bash
set -eu
umask 002
cd /data/raw/huzijian/project1_database
/usr/bin/mkdir -p /data/raw/huzijian/project1_database/log/V6.2_execution /data/raw/huzijian/project1_database/tmp/v62_node11
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node11
export TEMP=/data/raw/huzijian/project1_database/tmp/v62_node11
export TMP=/data/raw/huzijian/project1_database/tmp/v62_node11
export XDG_CACHE_HOME=/data/raw/huzijian/project1_database/tmp/v62_node11/cache
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH=/data/raw/huzijian/project1_database/tools/runtime/lib
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
/data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v62/server_probe.py node11 > /data/raw/huzijian/project1_database/log/V6.2_execution/node11_probe.log 2>&1
