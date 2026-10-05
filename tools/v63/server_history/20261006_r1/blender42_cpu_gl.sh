#!/bin/bash
# Scoped software OpenGL; no NVIDIA EGL vendor is exposed to the Fog engine.
set -eu
ulimit -c 0
cd /data/raw/huzijian/project1_database
V63_SCRATCH="${V63_SCRATCH:-/data/raw/huzijian/project1_database/tmp/v63_node12}"
case "$V63_SCRATCH" in /data/raw/huzijian/project1_database/*) ;; *) exit 91 ;; esac
export TMPDIR="$V63_SCRATCH"
export TMP="$V63_SCRATCH"
export TEMP="$V63_SCRATCH"
export XDG_CACHE_HOME="$V63_SCRATCH/cache"
export XDG_CONFIG_HOME="$V63_SCRATCH/config"
export XDG_DATA_HOME="$V63_SCRATCH/data"
export CUDA_CACHE_PATH="$V63_SCRATCH/cuda_cache"
export OPTIX_CACHE_PATH="$V63_SCRATCH/optix_cache"
export __GL_SHADER_DISK_CACHE_PATH="$V63_SCRATCH/gl_shader_cache"
export MESA_SHADER_CACHE_DIR="$V63_SCRATCH/mesa_shader_cache"
export __EGL_VENDOR_LIBRARY_FILENAMES=/data/raw/huzijian/project1_database/tools/runtime/v63_mesa_cpu_r3/mesa_vendor.json
export LIBGL_DRIVERS_PATH=/data/raw/huzijian/project1_database/tools/runtime/v63_mesa_cpu_r3/lib/dri
export LIBGL_ALWAYS_SOFTWARE=true
export GALLIUM_DRIVER=llvmpipe
export EGL_PLATFORM=surfaceless
export LP_NUM_THREADS=8
export BLENDER_USER_RESOURCES="$V63_SCRATCH/blender_user"
export BLENDER_USER_CONFIG="$V63_SCRATCH/blender_user/config"
export BLENDER_USER_SCRIPTS="$V63_SCRATCH/blender_user/scripts"
export BLENDER_SYSTEM_RESOURCES=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2
export BLENDER_SYSTEM_DATAFILES=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/datafiles
export BLENDER_SYSTEM_SCRIPTS=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/scripts
export BLENDER_SYSTEM_PYTHON=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/python
export PATH=/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/4.2/python/bin:/usr/bin:/bin
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export VIRTUAL_ENV=/data/raw/huzijian/project1_database/tools/conda_env
/usr/bin/mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$BLENDER_USER_CONFIG" "$BLENDER_USER_SCRIPTS" "$CUDA_CACHE_PATH" "$OPTIX_CACHE_PATH" "$__GL_SHADER_DISK_CACHE_PATH" "$MESA_SHADER_CACHE_DIR"
exec /data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/lib/ld-linux-x86-64.so.2 --library-path /data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/lib:/data/raw/huzijian/project1_database/tools/runtime/v63_mesa_cpu_r3/lib:/data/raw/huzijian/project1_database/tools/conda_env/lib:/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/lib:/data/raw/huzijian/project1_database/tools/runtime/lib /data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/blender "$@"
