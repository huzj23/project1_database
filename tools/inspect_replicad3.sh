#!/usr/bin/env bash
# ReplicaCAD ships scene/stage configs that may already describe prop layouts.
# If so we do not have to place furniture by hand.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
R="$WS/models/backgrounds/replicad"

for d in scenes stages objects lighting ssd; do
  echo "=== configs/$d ==="
  ls "$R/configs/$d" 2>/dev/null | head -8 | sed 's/^/  /'
  echo "    (total: $(ls "$R/configs/$d" 2>/dev/null | wc -l))"
done

echo
echo "=== a scene config sample ==="
f=$(find "$R/configs/scenes" -type f 2>/dev/null | head -1)
echo "  file: $f"
[ -n "$f" ] && head -40 "$f" | sed 's/^/  /'

echo
echo "=== stage config sample ==="
g=$(find "$R/configs/stages" -type f 2>/dev/null | head -1)
echo "  file: $g"
[ -n "$g" ] && head -30 "$g" | sed 's/^/  /'
