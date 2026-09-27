#!/usr/bin/env bash
# ===========================================================================
# Use the SAME simulation+validation path as the established tools/preflight_full3.sh,
# so the regression measures what the pipeline actually runs.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== how preflight_full3.sh simulates + validates ==="
sed -n '20,80p' "$WS/tools/preflight_full3.sh" | cat -n | sed 's/^/  /'
