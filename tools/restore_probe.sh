#!/usr/bin/env bash
# Restore the two probe settings that were left degraded from debugging.
#   free_fall_gso.yaml resolution   [480, 270] -> [1920, 1080]
#   server.yaml        samples_per_pixel  8 -> 24
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

cp "$REPO/configs/scenarios/free_fall_gso.yaml" "$WS/tmp/free_fall_gso.yaml.bak"
cp "$REPO/configs/server.yaml" "$WS/tmp/server.yaml.bak"

sed -i 's/^  resolution: \[480, 270\]/  resolution: [1920, 1080]/' \
    "$REPO/configs/scenarios/free_fall_gso.yaml"
sed -i 's/^samples_per_pixel: 8/samples_per_pixel: 24/' "$REPO/configs/server.yaml"

echo "=== after restore ==="
echo "  free_fall_gso.yaml:"
grep -n 'resolution' "$REPO/configs/scenarios/free_fall_gso.yaml" | sed 's/^/    /'
echo "  server.yaml:"
grep -n 'samples_per_pixel\|scenario_config' "$REPO/configs/server.yaml" | sed 's/^/    /'

echo
echo "=== indoor-critical values (must be untouched) ==="
echo "  replicad_apartment visual.mesh:"
grep -n 'mesh:\|object_name:\|lighting_source:' \
    "$REPO/assets/environments/replicad_apartment/asset.yaml" | sed 's/^/    /'
echo "  maps.yaml pinned region:"
grep -n 'position:\|bounds_xy:\|region_id:' "$REPO/configs/maps.yaml" | sed 's/^/    /'
