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
PROBE=/data/raw/huzijian/project1_database/tools/v5_probe_cozy_view.py
RENDER=/data/raw/huzijian/project1_database/tools/v5_render_cozy_background.py
OUT=/data/raw/huzijian/project1_database/outcomes/v5/cozy_kitchen_background
LOG=/data/raw/huzijian/project1_database/tmp/v5_probe_and_background.log
FFMPEG=/usr/bin/ffmpeg

exec > >(/usr/bin/tee "$LOG") 2>&1

/usr/bin/mkdir -p "$OUT/frames"
"$BLENDER" -b "$SOURCE" -t 8 --python "$PROBE"
"$BLENDER" -b "$SOURCE" -t 8 --python "$RENDER"
"$FFMPEG" -y -framerate 16 -i "$OUT/frames/frame_%04d.png" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart \
  "$OUT/cozy_kitchen_background.mp4"
/usr/bin/sha256sum "$OUT/cozy_kitchen_background.mp4"
/usr/bin/ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,avg_frame_rate,nb_frames \
  -of default=noprint_wrappers=1 "$OUT/cozy_kitchen_background.mp4"
/usr/bin/printf '%s\n' 'V5_BACKGROUND_DONE'
