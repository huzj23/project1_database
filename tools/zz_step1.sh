#!/usr/bin/env bash
# Step 1: rename the elephant, remove stray backup/derived files, check references.
set -uo pipefail
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
cd "$R" || exit 1
OLD="$R/assets/objects/gso_sootheze_cold_therapy_elephant"
NEW="$R/assets/objects/special_plush_elephant"

echo "=== reference check BEFORE deleting scene.glb / blend1 / baks ==="
echo "--- 'scene.glb' anywhere outside datasets/.git ---"
grep -rn 'scene\.glb' "$R" --exclude-dir=datasets --exclude-dir=.git 2>/dev/null || echo "  (no matches)"
echo "--- 'scene.blend1' ---"
grep -rn 'scene\.blend1' "$R" --exclude-dir=datasets --exclude-dir=.git 2>/dev/null || echo "  (no matches)"
echo "--- 't3dev-bak' ---"
grep -rn 't3dev-bak' "$R" --exclude-dir=datasets --exclude-dir=.git 2>/dev/null || echo "  (no matches)"
echo "--- manifest visual.mesh values in every asset.yaml ---"
find "$R/assets" -name asset.yaml | sort | while read -r f; do
  printf '  %s : ' "${f#$R/assets/}"
  grep -A1 '^visual:' "$f" | grep 'mesh:' | head -1
done
echo "--- does anything glob *.glb or list the visual dir? ---"
grep -rn '\*\.glb\|glob(' "$R/src" "$R/scripts" "$R/tests" 2>/dev/null || echo "  (no matches)"

echo
echo "=== RENAME ==="
if [ -d "$OLD" ]; then
  mv "$OLD" "$NEW" && echo "  renamed -> assets/objects/special_plush_elephant"
else
  echo "  OLD dir not present (already renamed?)"
fi

echo "=== DELETE stray files ==="
rm -fv "$NEW/asset.yaml.t3dev-bak"
rm -fv "$R/assets/environments/replicad_apartment/asset.yaml.t3dev-bak"
rm -fv "$R/assets/environments/replicad_apartment/visual/scene.blend1"
rm -fv "$R/assets/environments/replicad_apartment/visual/scene.glb"

echo
echo "=== mkdir source dirs ==="
mkdir -p "$NEW/source" "$R/assets/environments/replicad_apartment/source"
ls -la "$NEW" "$R/assets/environments/replicad_apartment"

echo
echo "=== sha256 of runtime visuals (unchanged files) ==="
sha256sum "$R/assets/environments/replicad_apartment/visual/scene.blend"
echo "=== sha256 of elephant visual ==="
sha256sum "$NEW/visual/model.obj"
