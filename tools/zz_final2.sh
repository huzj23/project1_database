#!/usr/bin/env bash
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== elephant: visual vs source original (must be byte-identical) ==="
sha256sum "$REPO/assets/objects/special_plush_elephant/visual/model.obj" \
          "$REPO/assets/objects/special_plush_elephant/source/visual_geometry.obj"
echo
echo "=== HF tooling present, unmodified ==="
sha256sum "$REPO/scripts/sync_hf_assets.py" "$REPO/docs/HUGGINGFACE_DATASET_CARD.md"
echo
echo "=== confirm the 11 failing assets are PRE-EXISTING (empty visual dirs) ==="
for a in food_lime sphere_baseball special_coffee_cup; do
  echo "  objects/$a/visual/ ->"; ls -A "$REPO/assets/objects/$a/visual/" 2>&1 | sed 's/^/      /'
  echo "  objects/$a/ contents ->"; ls -A "$REPO/assets/objects/$a/" 2>&1 | sed 's/^/      /'
done
echo "  environments/classroom/visual/ ->"; ls -A "$REPO/assets/environments/classroom/visual/" 2>&1 | sed 's/^/      /'
echo
echo "=== replicad scene.blend structural rules ==="
"$BLENDER" --background --factory-startup --python "$WS/tools/zz_blendcheck.py" -- \
  "$REPO/assets/environments/replicad_apartment/visual/scene.blend" 2>&1 \
  | grep -vE '^$|gvfs|Blender 3.4|Blender quit|Read blend|Warning'
