#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v63_node11
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export CUDA_VISIBLE_DEVICES=-1
export OMP_NUM_THREADS=8
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/archive_stills.py > /data/raw/huzijian/project1_database/tmp/v63_node11/archive_r1.log 2>&1
export V62_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node11/archive_scene_scratch_r1
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/save_final_scene.py > /data/raw/huzijian/project1_database/tmp/v63_node11/archive_scene_r1.log 2>&1
