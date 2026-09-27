#!/usr/bin/env bash
# Full ReplicaCAD prop inventory + how their collision is supplied.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
R="$WS/models/backgrounds/replicad"

echo "=== all 95 objects ==="
ls "$R/objects" | grep -v '^convex$' | sed 's/frl_apartment_//' | sed 's/\.glb$//' |
  paste -d' ' - - - | sed 's/^/  /'

echo
echo "=== collision assets ==="
echo "  objects/convex: $(ls "$R/objects/convex" 2>/dev/null | wc -l) files"
ls "$R/objects/convex" 2>/dev/null | head -4 | sed 's/^/    /'
echo "  urdf/: $(ls "$R/urdf" 2>/dev/null | wc -l) files"
ls "$R/urdf" 2>/dev/null | head -6 | sed 's/^/    /'

echo
echo "=== configs ==="
ls "$R/configs" 2>/dev/null | head -6 | sed 's/^/    /'

echo
echo "=== a sample urdf (what a prop looks like to the simulator) ==="
f=$(ls "$R/urdf"/*.urdf 2>/dev/null | head -1)
[ -n "$f" ] && head -24 "$f" | sed 's/^/    /'
