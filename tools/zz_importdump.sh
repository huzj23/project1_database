#!/usr/bin/env bash
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
"$BLENDER" --background --factory-startup --python "$WS/tools/zz_importdump.py" -- \
  "$REPO/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj" 2>&1 \
  | grep -vE 'Progress|^$|gvfs|Material not found|Blender 3.4|Blender quit|building geometries'
