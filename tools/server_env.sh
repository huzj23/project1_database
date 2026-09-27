#!/usr/bin/env bash
# Shared environment for every PhyCo-Sim job on the GPU server.
# Source this at the top of any script that runs inside tmux:
#
#     source /data/raw/huzijian/project1_database/tools/server_env.sh
#
# Why this exists: the machine's tmux *server* was started long ago by another
# session, so tmux sessions inherit a stale environment with **no proxy
# variables**.  Without the proxy, outbound HTTPS to some hosts (blender.org,
# pypi) fails with 403, while github happens to work -- which makes the failure
# look random.  Setting them explicitly makes every job deterministic.

export LC_ALL=C
export LANG=C

# --- outbound proxy (bound to localhost on this host) ------------------------
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="$no_proxy"

# --- project paths -----------------------------------------------------------
export WS="/data/raw/huzijian/project1_database"

# --- keep ALL scratch/temp files inside the workspace ------------------------
# Blender writes every rendered frame to a scratch dir; without this it lands in
# /tmp, which is outside the permitted tree (and on a small root filesystem).
export PHYCO_TMP="$WS/tmp"
export TMPDIR="$PHYCO_TMP"
export TEMP="$PHYCO_TMP"
export TMP="$PHYCO_TMP"
export BLENDER_USER_SCRIPTS="$WS/tmp/blender_scripts"
export XDG_CACHE_HOME="$WS/tmp/xdg_cache"
mkdir -p "$PHYCO_TMP" "$BLENDER_USER_SCRIPTS" "$XDG_CACHE_HOME" 2>/dev/null || true
export BLENDER="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
export BLENDER_PY="$WS/tools/runtime/blender-3.4.1-linux-x64/3.4/python/bin/python3.10"
export PHYCO_BLENDER="$BLENDER"

# Blender 3.4.1 needs libxkbcommon.so.0, which this CentOS 7 host lacks.  The
# library is vendored into the workspace (tools/vendor_libs.sh) rather than
# installed system-wide, so point the loader at it.
export PHYCO_LIBDIR="$WS/tools/runtime/lib"
if [ -d "$PHYCO_LIBDIR" ]; then
  export LD_LIBRARY_PATH="$PHYCO_LIBDIR:${LD_LIBRARY_PATH:-}"
fi

# --- render settings ---------------------------------------------------------
# CPU rendering is the DEFAULT and the intended path.
#
# Blender 3.4.1's CUDA path segfaults as soon as the Depth pass is enabled
# (reproduced deterministically for depth-only, image+depth and all-layers;
# RGB+segmentation alone is fine).  Depth is a required part of the annotation,
# so GPU rendering is unusable for this pipeline.  Even where it works the GPU
# is only ~13% faster on these scenes, while this node has 104 CPU cores.
#
# Set KUBRIC_USE_GPU=true explicitly only for depth-free experiments.
export KUBRIC_USE_GPU="${KUBRIC_USE_GPU:-false}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

# tensorflow is only used as a filesystem shim; keep it quiet and cheap
export TF_CPP_MIN_LOG_LEVEL=3
export TF_NUM_INTRAOP_THREADS=1
export PYTHONUNBUFFERED=1

# --- pip ---------------------------------------------------------------------
# NOTE: pypi.tuna.tsinghua.edu.cn returns HTTP 403 through this host's proxy
# (verified for every User-Agent), so the default index is pypi.org, with the
# aliyun mirror as a documented fallback.
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.org}"

# Blender's bundled CPython ships with NO CA trust store (ssl.get_default_verify_paths()
# returns cafile=None, capath=None), so every HTTPS request fails with
# CERTIFICATE_VERIFY_FAILED unless we point it at one.  A copy of the system
# bundle is kept inside the workspace by tools/vendor_libs.sh.
CA="$WS/tools/runtime/ca-bundle.crt"
if [ ! -f "$CA" ] && [ -f /etc/pki/tls/certs/ca-bundle.crt ]; then
  cp /etc/pki/tls/certs/ca-bundle.crt "$CA" 2>/dev/null || true
fi
if [ -f "$CA" ]; then
  export SSL_CERT_FILE="$CA"
  export REQUESTS_CA_BUNDLE="$CA"
  export CURL_CA_BUNDLE="$CA"
  export PIP_CERT="$CA"
fi
