#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
for a in food_apple food_lime food_lychee special_coffee_cup sphere_baseball gso_whey_protein_vanilla gso_mad_gab_refresh_card_game; do
  echo "===== $a ====="
  sed -n '/^visual:/,/^physics:/p' "$R/assets/objects/$a/asset.yaml" 2>/dev/null
done
echo "===== food_lime collision urdf ====="
cat "$R/assets/objects/food_lime/collision/model.urdf"
echo "===== gso_mad_gab collision urdf ====="
cat "$R/assets/objects/gso_mad_gab_refresh_card_game/collision/model.urdf"
echo "===== is assets/objects git-tracked? ====="
cd "$R" && git check-ignore -v assets/objects/food_lime/visual/model.glb assets/objects/food_lime/asset.yaml 2>&1 | head
echo "--- git status short ---"
git status --short 2>&1 | head -20
