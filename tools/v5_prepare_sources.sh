#!/bin/bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh

export KUBRIC_USE_GPU=false
export CUDA_VISIBLE_DEVICES=""

SOURCE_DIR=/data/raw/huzijian/project1_database/models/backgrounds/cozy_kitchen/source
SOURCE_BLEND=/data/raw/huzijian/project1_database/models/backgrounds/cozy_kitchen/source/blender-3.5-splash.blend
AUDIT_SCRIPT=/data/raw/huzijian/project1_database/tools/v5_inspect_cozy_kitchen.py
LOG=/data/raw/huzijian/project1_database/tmp/v5_prepare_sources.log

exec > >(/usr/bin/tee "$LOG") 2>&1

/usr/bin/mkdir -p "$SOURCE_DIR"
if [ ! -s "$SOURCE_BLEND" ]; then
  /usr/bin/curl -L --fail --retry 3 \
    https://download.blender.org/demo/splash/blender-3.5-splash.blend \
    -o "$SOURCE_BLEND"
fi

/usr/bin/printf '%s\n' '=== source checksum ==='
/usr/bin/sha256sum "$SOURCE_BLEND"
/usr/bin/printf '%s\n' '=== source size ==='
/usr/bin/stat -c '%s bytes' "$SOURCE_BLEND"
/usr/bin/printf '%s\n' '=== Blender source audit (CPU only) ==='
/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender \
  -b "$SOURCE_BLEND" --python "$AUDIT_SCRIPT"
/usr/bin/printf '%s\n' 'SOURCE_PREP_DONE'
