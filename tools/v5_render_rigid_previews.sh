#!/bin/bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export KUBRIC_USE_GPU=false
export CUDA_VISIBLE_DEVICES=""

BLENDER=/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender
SOURCE=/data/raw/huzijian/project1_database/models/backgrounds/cozy_kitchen/source/blender-3.5-splash.blend
SCRIPT=/data/raw/huzijian/project1_database/tools/v5_render_rigid_video.py
LOG=/data/raw/huzijian/project1_database/tmp/v5_render_rigid_previews.log

exec > >(/usr/bin/tee "$LOG") 2>&1
"$BLENDER" -b "$SOURCE" --python "$SCRIPT" -- --scenario drop --preview
"$BLENDER" -b "$SOURCE" --python "$SCRIPT" -- --scenario interaction --preview
/usr/bin/sha256sum \
  /data/raw/huzijian/project1_database/outcomes/v5/new_rigid_objects_drop/preview.png \
  /data/raw/huzijian/project1_database/outcomes/v5/nikon_hits_router_interaction/preview.png
/usr/bin/printf '%s\n' 'V5_RIGID_PREVIEWS_DONE'
