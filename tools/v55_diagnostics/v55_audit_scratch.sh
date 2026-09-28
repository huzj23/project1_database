#!/usr/bin/env bash
# READ-ONLY: the scratch-dir allocation region in pipeline.py.
export LC_ALL=C
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
echo "=== pipeline.py 240-290 ==="
sed -n '240,290p' src/physim/pipeline.py | cat -n | sed 's/^/  /'
echo
echo "=== pipeline.py _project_path + paths handling ==="
grep -n '_project_path' -A 10 src/physim/pipeline.py | head -30 | sed 's/^/  /'
echo
echo "=== config paths section (configs/server.yaml) ==="
grep -n 'paths' -A 12 configs/server.yaml | sed 's/^/  /'
