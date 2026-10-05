#!/bin/bash
set -euC
cd /data/raw/huzijian/project1_database
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/data/raw/huzijian/project1_database/tools/conda_env/bin/python -B /data/raw/huzijian/project1_database/tools/v63/inspect_render_r1.py 11 > /data/raw/huzijian/project1_database/tmp/v63_node11/render_resources_r1.log 2>&1
