#!/bin/bash
set -eu
cd /data/raw/huzijian/project1_database
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=2
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42.sh --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v62/geometry_audit.py > /data/raw/huzijian/project1_database/log/V6.2_execution/geometry_audit.log 2>&1
