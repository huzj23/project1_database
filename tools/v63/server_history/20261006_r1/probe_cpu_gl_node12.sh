#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V63_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node12
export CUDA_VISIBLE_DEVICES=-1
export OMP_NUM_THREADS=8
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v63/blender42_cpu_gl.sh --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/probe_cpu_gl.py > /data/raw/huzijian/project1_database/tmp/v63_node12/cpu_gl_probe_r1.log 2>&1
