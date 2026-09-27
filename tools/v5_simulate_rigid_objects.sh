#!/bin/bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export KUBRIC_USE_GPU=false
export CUDA_VISIBLE_DEVICES=""

/data/raw/huzijian/project1_database/tools/conda_env/bin/python \
  /data/raw/huzijian/project1_database/tools/v5_simulate_rigid_objects.py \
  > /data/raw/huzijian/project1_database/tmp/v5_simulate_rigid_objects.log 2>&1
/usr/bin/sha256sum \
  /data/raw/huzijian/project1_database/outcomes/v5/physics/new_rigid_objects_drop.json \
  /data/raw/huzijian/project1_database/outcomes/v5/physics/nikon_hits_router.json \
  >> /data/raw/huzijian/project1_database/tmp/v5_simulate_rigid_objects.log
/usr/bin/printf '%s\n' 'V5_SIMULATION_JOB_DONE' \
  >> /data/raw/huzijian/project1_database/tmp/v5_simulate_rigid_objects.log
