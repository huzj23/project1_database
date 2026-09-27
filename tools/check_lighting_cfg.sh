#!/usr/bin/env bash
# Which lighting config does each v3 stage declare?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
R="$WS/models/backgrounds/replicad"

echo "=== available lighting configs ==="
ls "$R/configs/lighting" | sed 's/^/  /'

echo
echo "=== default_lighting declared by each scene instance ==="
for i in 0 1 2 3; do
  f=$(ls "$R/configs/scenes/v3_sc${i}_staging_"*.scene_instance.json 2>/dev/null | head -1)
  printf '  sc%s: ' "$i"
  if [ -n "$f" ]; then
    grep -m1 'default_lighting' "$f" || echo "(none declared)"
  else
    echo "(no scene instance)"
  fi
done

echo
echo "=== and for frl ==="
grep -m1 'default_lighting' "$R/configs/scenes/apt_0.scene_instance.json" | sed 's/^/  /'
