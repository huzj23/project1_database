#!/usr/bin/env bash
# What are the 6 GSO actors actually like (mass, restitution, material class)?
# This drives which actor suits which motion.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

for d in "$REPO"/assets/objects/gso_*; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  echo "--- $name ---"
  grep -E 'material_class|mass_range|restitution_range|friction_range|^  type:|radius|half_extents' \
      "$d/asset.yaml" 2>/dev/null | sed 's/^/    /'
done

echo
echo "=== sphere/food actors (from the mentor repo) ==="
for d in "$REPO"/assets/objects/sphere_* "$REPO"/assets/objects/food_*; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  echo "--- $name ---"
  grep -E 'material_class|mass_range|restitution_range|^  type:|radius' "$d/asset.yaml" 2>/dev/null | sed 's/^/    /'
done

echo
echo "=== the three scenario configs (what motions already exist) ==="
for f in free_fall constant_force rolling; do
  echo "--- $f.yaml ---"
  sed 's/^/    /' "$REPO/configs/scenarios/$f.yaml" 2>/dev/null | head -45
done
