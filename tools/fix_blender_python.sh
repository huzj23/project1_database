#!/usr/bin/env bash
# The pipeline runs under Blender's bundled Python, which has no PyYAML.
# Install it into THAT interpreter (not the workspace conda env, which Blender
# does not use), then re-run the smoke test.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
BLPY="$WS/tools/runtime/blender-3.4.1-linux-x64/3.4/python/bin/python3.10"

echo "=== blender python ==="
ls -la "$BLPY" 2>/dev/null || echo "  not at expected path"
"$BLPY" -c "import sys; print('  version:', sys.version.split()[0]); print('  prefix:', sys.prefix)"

echo
echo "=== install PyYAML into blender's python ==="
"$BLPY" -m pip install --no-cache-dir "PyYAML>=6.0,<7" 2>&1 | tail -3

echo
echo "=== verify import ==="
"$BLPY" -c "import yaml; print('  yaml', yaml.__version__)"

echo
echo "=== also make the project importable from blender ==="
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
if [ ! -e "$BLPY" ]; then exit 1; fi
SP=$("$BLPY" -c "import site; print(site.getsitepackages()[0])")
echo "  site-packages: $SP"
echo "$REPO/src" > "$SP/physim_project.pth"
echo "  wrote .pth pointing at $REPO/src"
"$BLPY" -c "import physim; print('  physim import OK:', physim.__file__)"
