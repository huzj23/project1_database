#!/usr/bin/env bash
# ===========================================================================
# Print the EXACT text of every region I intend to patch, so the edits are literal
# and verifiable rather than guessed.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== assets/__init__.py lines 330-380 (_material incl. return) ==="
sed -n '330,380p' src/physim/assets/__init__.py | cat -n | sed 's/^/  /'

echo
echo "=== assets/__init__.py MaterialSpec dataclass (37-62) ==="
sed -n '37,62p' src/physim/assets/__init__.py | cat -n | sed 's/^/  /'

echo
echo "=== materials.py find_texture_dir (exact) ==="
grep -n 'def find_texture_dir' -A 14 src/physim/render/materials.py | sed 's/^/  /'

echo
echo "=== materials.py imports + MaterialSpec usage ==="
sed -n '30,40p' src/physim/render/materials.py | sed 's/^/  /'

echo
echo "=== turntable/asset.yaml FULL ==="
cat -n assets/objects/turntable/asset.yaml | sed 's/^/  /'
