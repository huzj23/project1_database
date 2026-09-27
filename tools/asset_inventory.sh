#!/usr/bin/env bash
# Inventory of all fetched assets.
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== PBR materials (Poly Haven, CC0) ==="
find "$WS/models/pbr_textures" -type d -name '*.blend' 2>/dev/null |
  sed "s#$WS/models/pbr_textures/##" | sort | sed 's/^/  /'
echo "  -- map counts --"
for d in $(find "$WS/models/pbr_textures" -type d -name '*.blend' 2>/dev/null | sort); do
  n=$(ls -1 "$d/textures" 2>/dev/null | wc -l)
  printf '  %-46s %d maps\n' "$(basename "$d")" "$n"
  ls -1 "$d/textures" 2>/dev/null | sed 's/^/       /'
done

echo
echo "=== HDRIs (Poly Haven, CC0) ==="
ls -la "$WS/models/hdri_hdr" 2>/dev/null | tail -n +4 | awk '{printf "  %-34s %6.1f MB\n", $9, $5/1048576}'

echo
echo "=== ReplicaCAD (CC BY-NC 4.0) ==="
echo "  stages : $(ls "$WS/models/backgrounds/replicad/stages" 2>/dev/null | wc -l)"
ls "$WS/models/backgrounds/replicad/stages" 2>/dev/null | sed 's/^/     /'
echo "  objects: $(ls "$WS/models/backgrounds/replicad/objects" 2>/dev/null | wc -l)"
echo "  urdf   : $(ls "$WS/models/backgrounds/replicad/urdf" 2>/dev/null | wc -l)"

echo
echo "=== GSO (CC BY-SA 4.0) ==="
echo "  objects: $(find "$WS/models/gso" -name object.urdf 2>/dev/null | wc -l)"
echo "  size   : $(du -sh "$WS/models/gso" 2>/dev/null | cut -f1)"

echo
echo "=== model tree total ==="
du -sh "$WS/models" 2>/dev/null | sed 's/^/  /'
df -h "$WS" 2>/dev/null | tail -1 | sed 's/^/  /'
