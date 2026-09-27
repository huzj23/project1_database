#!/usr/bin/env bash
# ===========================================================================
# Review focused ONLY on OUR OWN assets:
#   scene   : ReplicaCAD (models/backgrounds/replicad) -- our download
#   objects : GSO 140 downloaded + turntable we generated
# Mentor assets (basketball_court / classroom / street / sphere_* / food_*)
# are OUT OF SCOPE.
#
# Two questions:
#   A) can we export MORE scenes from our own ReplicaCAD download?
#      (5 stages x 21 layouts = scene variety from our own asset)
#   B) does replicad_apartment expose a table_top surface for the turntable?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
R="$WS/models/backgrounds/replicad"

echo "=== A) our own ReplicaCAD inventory ==="
echo "  stages (our download):"
ls -1 "$R/stages" | sed 's/^/    /'
echo "  total layouts: $(ls -1 "$R/configs/scenes" | wc -l)"
echo "  apt_* layouts: $(ls -1 "$R/configs/scenes"/apt_*.json 2>/dev/null | wc -l)"
echo "  v3_sc* layouts: $(ls -1 "$R/configs/scenes"/v3_sc*.json 2>/dev/null | wc -l)"
echo "  lighting configs: $(ls -1 "$R/configs/lighting" | wc -l)"
echo "  prop GLBs: $(ls -1 "$R/objects"/*.glb 2>/dev/null | wc -l)"

echo
echo "=== B) surfaces declared for replicad_apartment in maps.yaml ==="
sed -n '/replicad_apartment:/,$p' "$REPO/configs/maps.yaml" | sed 's/^/  /'

echo
echo "=== B2) is 'table_top' a surface_type anywhere in maps.yaml? ==="
grep -n 'surface_type' "$REPO/configs/maps.yaml" | sed 's/^/  /'

echo
echo "=== B3) what surface types does rolling.yaml allow? ==="
grep -n -A3 'surface:' "$REPO/configs/scenarios/rolling.yaml" | sed 's/^/  /'
