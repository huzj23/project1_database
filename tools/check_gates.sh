#!/usr/bin/env bash
# Last two acceptance-gate details before writing the plan.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== supported_fraction threshold: is it 0.9? benchmark gave 0.6875 but valid=True ==="
grep -n 'supported_fraction\|require_supported\|0.9' "$REPO/src/physim/validation/__init__.py" | sed 's/^/  /'

echo
echo "=== validate_free_fall: the actual gates ==="
sed -n '174,222p' "$REPO/src/physim/validation/__init__.py" | sed 's/^/  /'

echo
echo "=== validate_free_fall_soft (our addition) ==="
sed -n '222,278p' "$REPO/src/physim/validation/__init__.py" | sed 's/^/  /'
