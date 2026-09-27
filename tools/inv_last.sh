#!/usr/bin/env bash
# Remaining unknowns for the plan:
#  - do the spheres have textures (they have no visual/ dir)?
#  - what is the CLI signature of generate.py?
#  - full text of our working free_fall_gso.yaml
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== sphere_basketball asset.yaml (full) ==="
cat "$REPO/assets/objects/sphere_basketball/asset.yaml" 2>/dev/null | sed 's/^/  /'
echo "  --- files ---"
find "$REPO/assets/objects/sphere_basketball" -type f | sed "s|$REPO/assets/objects/sphere_basketball/|    |"

echo
echo "=== any sphere textures anywhere? ==="
find "$WS" -iname '*basketball*' -o -iname '*football*' 2>/dev/null | grep -viE '\.pyc|__pycache__' | head -12 | sed "s|$WS/|  |"

echo
echo "=== generate.py CLI ==="
grep -n 'add_argument\|def main' "$REPO/scripts/generate.py" 2>/dev/null | head -30 | sed 's/^/  /'

echo
echo "=== free_fall_gso.yaml (our working config, full) ==="
cat "$REPO/configs/scenarios/free_fall_gso.yaml" 2>/dev/null | sed 's/^/  /'
