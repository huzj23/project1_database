#!/bin/bash
set -eu
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V62_SCRATCH=/data/raw/huzijian/project1_database/tmp/v62_node12
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node12
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
export CUDA_VISIBLE_DEVICES=GPU-76330662-90bb-222e-1f50-1808f9771d73
export OMP_NUM_THREADS=12
/data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v62/check_idle_node.py > /data/raw/huzijian/project1_database/tmp/v62_node12/pilot_r4_resources.json
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42.sh --background --factory-startup --disable-autoexec --threads 12 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v62/pilot_render_r4.py > /data/raw/huzijian/project1_database/tmp/v62_node12/pilot_render_r4.log 2>&1
