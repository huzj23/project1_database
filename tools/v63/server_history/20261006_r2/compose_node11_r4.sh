#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V63_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node11/compose_trial_r4
export CUDA_VISIBLE_DEVICES=-1
export OMP_NUM_THREADS=16
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v63/blender42_cpu_gl_r3.sh --background --factory-startup --disable-autoexec --threads 16 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/compose_static_r4.py -- --layout /data/raw/huzijian/project1_database/tmp/v63_node11/layout_r6/layout.json --out /data/raw/huzijian/project1_database/tmp/v63_node11/static_scene_r4 > /data/raw/huzijian/project1_database/tmp/v63_node11/compose_r4.log 2>&1
