#!/usr/bin/env bash
# Same decisive test, with the correct AssetManager signature.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== AssetManager signature ==="
grep -n 'def __init__' -A6 "$REPO/src/physim/assets/__init__.py" | head -20 | sed 's/^/  /'
echo
echo "=== MapManager signature ==="
grep -n 'def __init__' -A6 "$REPO/src/physim/maps/__init__.py" | head -14 | sed 's/^/  /'
echo
echo "=== how does pipeline.py construct them? ==="
grep -n 'AssetManager(\|MapManager(\|asset_root' "$REPO/src/physim/pipeline.py" | head -12 | sed 's/^/  /'
