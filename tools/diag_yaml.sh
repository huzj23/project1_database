#!/usr/bin/env bash
# Inspect the appended block with visible indentation and validate.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== tail of maps.yaml with visible leading spaces ==="
tail -35 configs/maps.yaml | cat -A | sed 's/\$$//' | head -40

echo
echo "=== yaml error detail ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
try:
    yaml.safe_load(open('configs/maps.yaml'))
    print('  parses OK')
except Exception as e:
    print('  ERROR:', e)
"
