#!/bin/bash
# Only this process uses the isolated loader. No shared or system library changes.
set -eu
ulimit -c 0
cd /data/raw/huzijian/project1_database
V62_SCRATCH="${V62_SCRATCH:-/data/raw/huzijian/project1_database/tmp/v62_node11}"
case "$V62_SCRATCH" in /data/raw/huzijian/project1_database/*) ;; *) exit 91 ;; esac
export TMPDIR="$V62_SCRATCH"
export TEMP="$V62_SCRATCH"
export TMP="$V62_SCRATCH"
export XDG_CACHE_HOME="$V62_SCRATCH/cache"
export XDG_CONFIG_HOME="$V62_SCRATCH/config"
export XDG_DATA_HOME="$V62_SCRATCH/data"
export BLENDER_USER_RESOURCES="$V62_SCRATCH/blender_user"
export BLENDER_USER_CONFIG="$V62_SCRATCH/blender_user/config"
export BLENDER_USER_SCRIPTS="$V62_SCRATCH/blender_user/scripts"
export BLENDER_SYSTEM_RESOURCES=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2
export BLENDER_SYSTEM_DATAFILES=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/datafiles
export BLENDER_SYSTEM_SCRIPTS=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/scripts
export BLENDER_SYSTEM_PYTHON=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/python
export PATH=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/python/bin:/usr/bin:/bin
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
/usr/bin/mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$BLENDER_USER_CONFIG" "$BLENDER_USER_SCRIPTS"
exec /data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/lib/ld-linux-x86-64.so.2 --library-path /data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/lib:/data/raw/huzijian/project1_database/tools/conda_env/lib:/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/lib:/data/raw/huzijian/project1_database/tools/runtime/lib /data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/blender "$@"
