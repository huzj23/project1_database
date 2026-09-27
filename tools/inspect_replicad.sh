#!/usr/bin/env bash
# What is actually inside the ReplicaCAD download?
#
# The stages are "emptied of all but architectural features", which is why our D
# renders look bare.  If the same download also ships the furniture library, we
# can place real everyday props back into the room -- that is the cheapest route
# to a scene with everyday reference objects.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
R="$WS/models/backgrounds/replicad"

echo "=== top-level ==="
ls "$R" | sed 's/^/  /'

echo
echo "=== objects/ ==="
n=$(ls "$R/objects" 2>/dev/null | wc -l)
echo "  count: $n"
ls "$R/objects" 2>/dev/null | head -40 | sed 's/^/    /'

echo
echo "=== category breakdown (from names) ==="
ls "$R/objects" 2>/dev/null |
  sed -E 's/^(frl_apartment_)?//' |
  sed -E 's/_(0[0-9]|[0-9]+)?\.?.*$//' |
  sort | uniq -c | sort -rn | head -22 | sed 's/^/    /'

echo
echo "=== urdf/ and configs ==="
ls "$R/urdf" 2>/dev/null | head -8 | sed 's/^/    /'
find "$R" -maxdepth 1 -name '*.json' -o -maxdepth 1 -name '*.yaml' 2>/dev/null | sed 's/^/    /'
