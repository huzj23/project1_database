#!/bin/bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export KUBRIC_USE_GPU=false
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

BLENDER=/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender
SOURCE=/data/raw/huzijian/project1_database/models/backgrounds/cozy_kitchen/source/blender-3.5-splash.blend
SCRIPT=/data/raw/huzijian/project1_database/tools/v5_render_rigid_video.py
FFMPEG=/usr/bin/ffmpeg
FFPROBE=/usr/bin/ffprobe
LOG=/data/raw/huzijian/project1_database/tmp/v5_render_rigid_videos.log

exec > >(/usr/bin/tee "$LOG") 2>&1

"$BLENDER" -b "$SOURCE" -t 8 --python "$SCRIPT" -- --scenario drop
DROP=/data/raw/huzijian/project1_database/outcomes/v5/new_rigid_objects_drop
"$FFMPEG" -y -framerate 16 -i "$DROP/frames/frame_%04d.png" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart \
  "$DROP/new_rigid_objects_drop.mp4"

"$BLENDER" -b "$SOURCE" -t 8 --python "$SCRIPT" -- --scenario interaction
INTERACTION=/data/raw/huzijian/project1_database/outcomes/v5/nikon_hits_router_interaction
"$FFMPEG" -y -framerate 16 -i "$INTERACTION/frames/frame_%04d.png" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart \
  "$INTERACTION/nikon_hits_router_interaction.mp4"

/usr/bin/sha256sum \
  "$DROP/new_rigid_objects_drop.mp4" \
  "$INTERACTION/nikon_hits_router_interaction.mp4"
"$FFPROBE" -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,avg_frame_rate,nb_frames \
  -of default=noprint_wrappers=1 "$DROP/new_rigid_objects_drop.mp4"
"$FFPROBE" -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,avg_frame_rate,nb_frames \
  -of default=noprint_wrappers=1 "$INTERACTION/nikon_hits_router_interaction.mp4"
/usr/bin/printf '%s\n' 'V5_RIGID_VIDEOS_DONE'
