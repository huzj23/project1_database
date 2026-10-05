#!/bin/bash
set -euC
cd /data/raw/huzijian/project1_database
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/inspect_render_r2.py 12 v63_stills_gpu_r1 > /data/raw/huzijian/project1_database/tmp/v63_node12/render_resources_r2.log 2>&1
