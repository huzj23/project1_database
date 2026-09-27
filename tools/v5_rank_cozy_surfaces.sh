#!/bin/bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export KUBRIC_USE_GPU=false
export CUDA_VISIBLE_DEVICES=""

/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender \
  -b /data/raw/huzijian/project1_database/models/backgrounds/cozy_kitchen/source/blender-3.5-splash.blend \
  --python /data/raw/huzijian/project1_database/tools/v5_rank_cozy_surfaces.py \
  > /data/raw/huzijian/project1_database/tmp/v5_rank_cozy_surfaces.log 2>&1
/usr/bin/printf '%s\n' 'V5_SURFACE_RANK_DONE' \
  >> /data/raw/huzijian/project1_database/tmp/v5_rank_cozy_surfaces.log
