#!/usr/bin/env bash
# Finish the inventory: what exported scenes do we actually have on disk?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== all scene.blend on the server (excluding tmp) ==="
find "$WS" -name 'scene.blend' -not -path '*/tmp/*' 2>/dev/null | while read f; do
  printf "  %8.1f MB  %s\n" "$(echo "scale=1; $(stat -c%s "$f")/1048576" | bc)" "${f#$WS/}"
done

echo
echo "=== all lighting configs ==="
ls -1 "$WS/models/backgrounds/replicad/configs/lighting" 2>/dev/null | sed 's/^/  /'

echo
echo "=== our scene export tools ==="
ls -1 "$WS/tools/" 2>/dev/null | grep -iE 'scene|blend|export|background' | sed 's/^/  /'

echo
echo "=== registered environments (assets.yaml) ==="
grep -nE '^\s+- id:|^\s+id:' "$REPO/configs/assets.yaml" 2>/dev/null | sed 's/^/  /'

echo
echo "=== maps.yaml: which regions exist ==="
grep -n 'region_id:' "$REPO/configs/maps.yaml" 2>/dev/null | sed 's/^/  /'
