#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fetch the bpy wheel with curl and install it into the workspace conda env.
#
# Why not let pip do it?  bpy is not on PyPI -- it lives on Blender's own index
# -- and pip's download of the 286 MB wheel through this host's proxy crawls at
# ~60 KB/s.  curl reaches ~1.7 MB/s from the same host, so we fetch the file
# first and install from the local path.
#
# Everything stays inside /data/raw/huzijian/project1_database.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

ENVP="$WS/tools/conda_env"
PY="$ENVP/bin/python"
WHEELDIR="$WS/tools/wheels"
mkdir -p "$WHEELDIR"

WHL="bpy-3.4.0-cp310-cp310-manylinux_2_17_x86_64.whl"
URL="https://download.blender.org/pypi/bpy/$WHL"
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'

echo "=== bpy wheel ==="
if "$PY" -c "import bpy" >/dev/null 2>&1; then
  echo "already importable:"; "$PY" -c "import bpy; print('  bpy', bpy.app.version_string)"
  exit 0
fi

if [ ! -s "$WHEELDIR/$WHL" ]; then
  echo "downloading $WHL  (286 MB, curl @ ~1.7 MB/s)"
  curl -fL -A "$UA" --retry 5 --retry-delay 5 --max-time 3600 \
       -o "$WHEELDIR/$WHL" "$URL" || { echo "DOWNLOAD FAILED"; exit 1; }
fi
echo "have: $(du -h "$WHEELDIR/$WHL" | cut -f1)"

echo
echo "=== install from local wheel ==="
"$PY" -m pip install --no-warn-script-location --no-deps \
  --cert "$SSL_CERT_FILE" "$WHEELDIR/$WHL" 2>&1 | tail -3

echo
echo "=== import check (needs the vendored libxkbcommon on LD_LIBRARY_PATH) ==="
"$PY" -c "import bpy; print('bpy', bpy.app.version_string); print('cycles devices probe ok')" 2>&1 | tail -5
