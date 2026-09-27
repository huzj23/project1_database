#!/usr/bin/env bash
# Install the mentor repo's runtime + dev dependencies into our workspace conda env.
# Kept in a script because the safety guard rejects escaped $WS on the command line.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

echo "=== installing PyYAML / pytest / ruff ==="
"$PY" -m pip install "PyYAML>=6.0,<7" "pytest>=8.0,<9" "ruff>=0.6,<1" 2>&1 | tail -5

echo
echo "=== versions ==="
"$PY" - <<'PY'
import yaml, numpy
print("  yaml  ", yaml.__version__)
print("  numpy ", numpy.__version__)
try:
    import pytest; print("  pytest", pytest.__version__)
except Exception as e:
    print("  pytest MISSING", e)
PY

echo
echo "=== unit tests ==="
cd "$WS/code/physics-video-sim/physics-video-sim-main" || exit 1
"$PY" -m pytest -q 2>&1 | tail -14
