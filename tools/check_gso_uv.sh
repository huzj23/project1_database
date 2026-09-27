#!/usr/bin/env bash
# Does the GSO OBJ carry UV coordinates?  (a texture with no UV map samples as black)
source /data/raw/huzijian/project1_database/tools/server_env.sh
G="$WS/models/gso/Sootheze_Cold_Therapy_Elephant/visual_geometry.obj"
echo "=== element counts ==="
awk '{print $1}' "$G" | sort | uniq -c | sort -rn | head -8 | sed 's/^/  /'
echo "=== first face line ==="
grep -m1 '^f ' "$G" | sed 's/^/  /'
echo "=== does any face reference vt? ==="
if grep -qE '^f +[0-9]+/[0-9]+' "$G"; then echo "  YES - texture coords present"; else echo "  NO  - faces have no vt indices -> texture cannot map"; fi
echo "=== texture file sanity ==="
python3 - <<PY
import struct
p = "$WS/models/gso/Sootheze_Cold_Therapy_Elephant/texture.png"
with open(p, "rb") as f:
    head = f.read(33)
print("  png signature ok:", head[:8] == b"\x89PNG\r\n\x1a\n")
if head[:8] == b"\x89PNG\r\n\x1a\n":
    w, h = struct.unpack(">II", head[16:24])
    print(f"  texture size: {w} x {h}")
PY
