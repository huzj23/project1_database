#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V62_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node11
export CUDA_VISIBLE_DEVICES=-1
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/build_common_assets.py > /data/raw/huzijian/project1_database/tmp/v63_node11/build_common_r1.log 2>&1
