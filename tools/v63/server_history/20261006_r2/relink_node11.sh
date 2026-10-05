#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V62_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node11/relink_archive_r1_scratch
export CUDA_VISIBLE_DEVICES=-1
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/relink_archive_scene.py > /data/raw/huzijian/project1_database/tmp/v63_node11/relink_archive_r1.log 2>&1
