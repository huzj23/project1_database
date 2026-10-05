#!/bin/bash
set -eu
cd /data/raw/huzijian/project1_database
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=2
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42.sh --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v62/inspect_source_v2.py -- /data/raw/huzijian/project1_database/log/V6.2_execution/source_4223_probe.json > /data/raw/huzijian/project1_database/log/V6.2_execution/source_4223_bound_probe.log 2>&1
