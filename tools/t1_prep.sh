#!/usr/bin/env bash
# T1 prep: the helper signatures and how assets are registered, so the two new
# yaml configs reference real asset ids and real helper keys.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== common.py helpers ==="
grep -n '^def ' "$REPO/src/physim/scenarios/common.py" | sed 's/^/  /'

echo
echo "=== timing_parameters + base_physics + object_extent ==="
sed -n '1,40p' "$REPO/src/physim/scenarios/common.py" | sed 's/^/  /'

echo
echo "=== assets.yaml registry (which ids are registered) ==="
cat "$REPO/configs/assets.yaml" | sed 's/^/  /'

echo
echo "=== asset.yaml of the 3 T1 actors ==="
for n in gso_whey_protein_vanilla gso_room_essentials_fabric_cube_lavender gso_down_to_earth_orchid_pot_ceramic_lime; do
  echo "--- $n ---"
  grep -E 'support_height|footprint_radius|radius:|material_class|mass_range|restitution_range|friction_range' \
      "$REPO/assets/objects/$n/asset.yaml" | sed 's/^/    /'
done
