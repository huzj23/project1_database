#!/usr/bin/env bash
# ===========================================================================
# V5.5 minimal project environment wrapper.
#
# 01_operations.md section 4 requires a REVIEWED, minimal environment wrapper rather
# than sourcing the historical tools/server_env.sh, which:
#   * defaults CUDA_VISIBLE_DEVICES to GPU 0 (V5.5 runs CPU), and
#   * tries to copy CA certificates from OUTSIDE the workspace.
#
# Policy enforced here:
#   * CPU only: CUDA_VISIBLE_DEVICES="" and KUBRIC_USE_GPU=false
#   * numeric libraries and Blender pinned to 8 threads
#   * every temp/cache/config path redirected INSIDE the workspace
#   * no auto-cleaning temporary-directory wrappers
#
# Usage:  source /data/raw/huzijian/project1_database/tools/v55_env.sh
# ===========================================================================

WS=/data/raw/huzijian/project1_database
export WS
export REPO="$WS/code/physics-video-sim/physics-video-sim-main"

# --- project runtimes (workspace-local only) -------------------------------
export PY="$WS/tools/conda_env/bin/python"
export BLENDER="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"

# The server's Blender 3.4.1 fails to start with
#   "error while loading shared libraries: libxkbcommon.so.0"
# because CentOS 7 does not ship it.  The project's OWN tools/runtime/lib supplies
# it, so prepend that directory -- this does NOT touch system libraries or require
# a server OS upgrade (which 09 explicitly forbids).
export LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}"

# --- CPU-only execution ----------------------------------------------------
export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU=false
export NVIDIA_VISIBLE_DEVICES=""

# --- thread caps (single heavy task, max 8 threads) ------------------------
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export NUMEXPR_NUM_THREADS=8
export VECLIB_MAXIMUM_THREADS=8
export BLENDER_THREADS=8

# --- all temp/cache inside the workspace ----------------------------------
export TMPDIR="$WS/tmp"
export TMP="$WS/tmp"
export TEMP="$WS/tmp"
export XDG_CACHE_HOME="$WS/tmp/xdg_cache"
export XDG_CONFIG_HOME="$WS/tmp/xdg_config"
export XDG_DATA_HOME="$WS/tmp/xdg_data"
export PIP_CACHE_DIR="$WS/tmp/pip_cache"
export HF_HOME="$WS/tmp/hf_home"
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONPYCACHEPREFIX="$WS/tmp/pycache"
export BLENDER_USER_CONFIG="$WS/tmp/blender_config"
export BLENDER_USER_SCRIPTS="$WS/tmp/blender_scripts"
export BLENDER_USER_DATAFILES="$WS/tmp/blender_datafiles"

# --- workspace discovery for the no-delete layer --------------------------
export PHYSIM_WORKSPACE_ROOT="$WS"

# --- no auto-deleting temp wrappers (V5.5 forbids file deletion) -----------
#    Kubric/Blender honour these to avoid removing scratch on exit.
export KUBRIC_KEEP_SCRATCH=1
export PYTHONDONTWRITEBYTECODE=1

mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" \
         "$BLENDER_USER_CONFIG" "$BLENDER_USER_SCRIPTS" "$BLENDER_USER_DATAFILES" \
         "$WS/remove"

# --- tmux socket for this project only ------------------------------------
export V55_SOCK="$WS/tmp/tmux_v55.sock"

# --- locale: force ASCII-safe output for log capture ----------------------
export LC_ALL=C
export LANG=C
