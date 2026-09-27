#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== food_lime/asset.yaml ==="
cat "$R/assets/objects/food_lime/asset.yaml"
echo "=== classroom/asset.yaml ==="
cat "$R/assets/environments/classroom/asset.yaml"
echo "=== elephant tree ==="
find "$R/assets/objects/gso_sootheze_cold_therapy_elephant" -printf '%y %10s %p\n' | sort -k3
echo "=== replicad tree ==="
find "$R/assets/environments/replicad_apartment" -printf '%y %10s %p\n' | sort -k3
echo "=== objects dir listing ==="
ls -la "$R/assets/objects/"
echo "=== environments dir listing ==="
ls -la "$R/assets/environments/"
