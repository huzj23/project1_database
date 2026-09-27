#!/usr/bin/env bash
# CRITICAL: do the mentor's 3 scenes actually have their visual files?
# The manifests reference visual/scene.blend but the directories are only 40-384K,
# while replicad_apartment (which HAS a real scene.blend) is 175M.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== every file under each environment dir ==="
for e in basketball_court classroom street replicad_apartment; do
  echo "--- $e ---"
  find "$REPO/assets/environments/$e" -type f 2>/dev/null | while read f; do
    printf "    %8d  %s\n" "$(stat -c%s "$f")" "${f#$REPO/assets/environments/$e/}"
  done
done

echo
echo "=== which scenario python files exist? ==="
ls -1 "$REPO/src/physim/scenarios/" 2>/dev/null | sed 's/^/  /'

echo
echo "=== which validators exist? ==="
ls -1 "$REPO/src/physim/validation/" 2>/dev/null | sed 's/^/  /'

echo
echo "=== registered scenarios (how does the code discover them?) ==="
grep -rn 'free_fall\|constant_force\|rolling\|projectile\|turntable' \
    "$REPO/src/physim/scenarios/__init__.py" 2>/dev/null | head -20 | sed 's/^/  /'
