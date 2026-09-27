#!/usr/bin/env bash
# Do basketball_court / classroom / street have usable VISUAL assets on the server?
# V2.0 §6.1 claims they are real 3D scenes (969 meshes etc).  If true, we do not
# need HDRI backdrops at all -- and they have parallax, which HDRI cannot provide.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

for e in basketball_court classroom street replicad_apartment; do
  echo "=========== $e ==========="
  d="$REPO/assets/environments/$e"
  find "$d" -maxdepth 2 -type f 2>/dev/null | sed "s|$d/|    |" | head -20
  echo "    --- manifest ---"
  grep -E 'mesh:|object_name:|type:|center:|half_extents:|size:|lighting_source' "$d/asset.yaml" 2>/dev/null | sed 's/^/      /'
  echo
done

echo "=== total size of each environment dir ==="
for e in basketball_court classroom street replicad_apartment; do
  d="$REPO/assets/environments/$e"
  s=$(du -sh "$d" 2>/dev/null | cut -f1)
  echo "  $e: $s"
done
