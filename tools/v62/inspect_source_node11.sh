#!/bin/bash
set -eu
ulimit -c 0
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node11
export TEMP=/data/raw/huzijian/project1_database/tmp/v62_node11
export XDG_CACHE_HOME=/data/raw/huzijian/project1_database/tmp/v62_node11/cache
export BLENDER_USER_CONFIG=/data/raw/huzijian/project1_database/tmp/v62_node11/blender_config
export BLENDER_USER_SCRIPTS=/data/raw/huzijian/project1_database/tmp/v62_node11/blender_scripts
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH=/data/raw/huzijian/project1_database/tools/runtime/lib
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=2
/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender --background --factory-startup --threads 2 --python /data/raw/huzijian/project1_database/tools/v62/inspect_source.py > /data/raw/huzijian/project1_database/log/V6.2_execution/source_341_probe.log 2>&1
