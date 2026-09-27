#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Create a conda environment INSIDE the project workspace and install the
# simulation dependencies into it.
#
# Everything conda writes is redirected into the workspace so the shared
# machine is untouched:
#   env prefix  : <ws>/tools/conda_env
#   pkg cache   : <ws>/tools/conda_pkgs
#   envs dir    : <ws>/tools/conda_envs
#   user config : <ws>/tools/home/.condarc        (HOME is overridden)
#
# The conda *executable* itself is read-only system tooling; no file outside the
# workspace is created or modified.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

CONDA_BIN="/data/raw/wangzile/miniconda3/bin/conda"
ENVP="$WS/tools/conda_env"
PY="$ENVP/bin/python"

# --- keep every conda side-effect inside the workspace ----------------------
export HOME="$WS/tools/home"
export CONDARC="$HOME/.condarc"
export CONDA_PKGS_DIRS="$WS/tools/conda_pkgs"
export CONDA_ENVS_PATH="$WS/tools/conda_envs"
mkdir -p "$HOME" "$CONDA_PKGS_DIRS" "$CONDA_ENVS_PATH"

cat > "$CONDARC" <<'YAML'
channels:
  - defaults
show_channel_urls: true
always_yes: true
YAML

echo "=== channel reachability ==="
for u in \
  "https://repo.anaconda.com/pkgs/main/noarch/repodata.json" \
  "https://conda.anaconda.org/conda-forge/noarch/repodata.json" \
  "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/noarch/repodata.json" \
  "https://mirrors.bfsu.edu.cn/anaconda/pkgs/main/noarch/repodata.json"
do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$u" || echo ERR)
  printf '  %-4s %s\n' "$code" "$u"
done

echo
echo "=== conda info ==="
"$CONDA_BIN" --version

echo
echo "=== create env at $ENVP ==="
if [ -x "$PY" ]; then
  echo "already exists: $("$PY" --version 2>&1)"
else
  "$CONDA_BIN" create -y -p "$ENVP" python=3.10 pip || { echo "CONDA CREATE FAILED"; exit 1; }
fi
"$PY" --version || exit 1
"$PY" -m pip --version

echo
echo "=== install dependencies ==="
# --only-binary is essential: without it pip falls back to building sdists
# (h5py, pandas) which needs compilers and a working build isolation sandbox,
# and the resulting failures are opaque.  Wheel-only keeps it deterministic.
PIPOPT=(--no-warn-script-location --only-binary=:all:
        --retries 5 --timeout 60
        -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST")
[ -f "$SSL_CERT_FILE" ] && PIPOPT+=(--cert "$SSL_CERT_FILE")
"$PY" -m pip install "${PIPOPT[@]}" --upgrade pip setuptools wheel 2>&1 | tail -2

install_group() {
  local name="$1"; shift
  echo "  --- [$name] $*"
  "$PY" -m pip install "${PIPOPT[@]}" "$@" 2>&1 | tail -2
}

# --- bpy -------------------------------------------------------------------
# Crucial detail: bpy wheels are NOT published on PyPI.  Blender hosts them on
# its own index, and only there will `bpy==3.4.0` resolve.
echo "  --- [bpy] bpy==3.4.0  (Blender PyPI index)"
BLPYPI="https://download.blender.org/pypi/"
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
if "$PY" -c "import bpy" >/dev/null 2>&1; then
  echo "      already installed"
else
  "$PY" -m pip install --no-warn-script-location --only-binary=:all: \
      --retries 5 --timeout 120 --cert "$SSL_CERT_FILE" \
      --index-url "$BLPYPI" --trusted-host download.blender.org \
      "bpy==3.4.0" 2>&1 | tail -3
fi

install_group core     "numpy==1.26.4"
install_group geo      "traitlets==5.16.1" "munch==4.0.0" "pyquaternion==0.9.9" \
                       "etils==1.13.0" "importlib_resources==7.1.0" "absl-py==2.5.0"
install_group tf       "tensorflow-cpu==2.15.1"
install_group vision   "opencv-python==4.10.0.84" "scikit-image==0.25.2" \
                       "scikit-learn==1.7.2" "matplotlib==3.10.9" \
                       "imageio==2.37.4" "pypng==0.20220715.0" "Pillow"
install_group exr      "OpenEXR==3.2.3" "Imath==0.0.2"
install_group mesh     "trimesh==5.1.0"
install_group misc     "loguru==0.7.3" "pandas==2.3.3" "tqdm==4.70.1" "requests"
install_group physics  "pybullet"

echo
echo "=== verify ==="
"$PY" - <<'PY'
import sys
print("python  ", sys.version.split()[0])
for mod in ("numpy", "pybullet", "OpenEXR", "cv2", "trimesh"):
    try:
        m = __import__(mod)
        print(f"{mod:9}", getattr(m, "__version__", "ok"))
    except Exception as e:
        print(f"{mod:9} FAILED: {type(e).__name__}: {e}")
try:
    import bpy
    print("bpy      ", bpy.app.version_string)
except Exception as e:
    print("bpy       FAILED:", type(e).__name__, e)
print("VERIFY DONE")
PY

echo
echo "=== inside-workspace check ==="
du -sh "$ENVP" "$CONDA_PKGS_DIRS" 2>/dev/null
echo "conda env python: $PY"
