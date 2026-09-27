#!/usr/bin/env bash
# ===========================================================================
# Facts needed to normalize our two assets per the mentor's conventions.
#
# The private repo already holds 11 assets (all the mentor's; none of ours):
#   basketball_court, classroom, street, food_apple, food_lime, food_lychee,
#   special_coffee_cup, sphere_baseball, sphere_basketball, sphere_football,
#   sphere_volleyball
# so we are ADDING, not overwriting.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== does the SERVER repo have the mentor's asset-prep scripts? ==="
for s in prepare_visual_asset.py generate_collision_mesh.py generate_environment_surface_collision.py \
         inspect_blend_asset.py inspect_glb.py preview_blender.py blender_preview_scene.py sync_hf_assets.py; do
  if [ -f "scripts/$s" ]; then
    printf "  YES  %-42s %s bytes\n" "$s" "$(wc -c < scripts/$s)"
  else
    printf "  NO   %s\n" "$s"
  fi
done

echo
echo "=== is our elephant visual identical to the GSO source? ==="
md5sum assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj \
       assets/objects/gso_sootheze_cold_therapy_elephant/visual/texture.png 2>/dev/null | sed 's/^/  /'
echo "  --- our model.mtl ---"
cat assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.mtl | sed 's/^/    /'
echo "  --- our visual/model.obj header (first 6 lines) ---"
head -6 assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj | sed 's/^/    /'

echo
echo "=== how is the environment referenced? (maps.yaml + configs) ==="
grep -n 'replicad_apartment' configs/maps.yaml | head -12 | sed 's/^/  /'
echo "  --- count of references across the repo ---"
grep -rl 'replicad_apartment' --include='*.yaml' --include='*.py' . 2>/dev/null | grep -v __pycache__ | sed 's/^/    /'
echo "  --- count of references to the elephant id ---"
grep -rl 'gso_sootheze_cold_therapy_elephant' --include='*.yaml' --include='*.py' . 2>/dev/null | grep -v __pycache__ | sed 's/^/    /'

echo
echo "=== maps.yaml: environment registration + surface groups ==="
sed -n '1,60p' configs/maps.yaml | sed 's/^/  /'

echo
echo "=== assets.yaml (registry) ==="
cat configs/assets.yaml | sed 's/^/  /'
