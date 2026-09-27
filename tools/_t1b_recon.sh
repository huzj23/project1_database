#!/usr/bin/env bash
# Recon: list repo layout and dump key files for the rolling-can task.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== A: repo top ==="
ls -la "$REPO" | head -40
echo "=== B: scenarios dir ==="
ls -la "$REPO/src/physim/scenarios"
echo "=== C: camera dir ==="
ls -la "$REPO/src/physim/camera"
echo "=== D: configs/scenarios ==="
ls -la "$REPO/configs/scenarios"
echo "=== E: configs top ==="
ls -la "$REPO/configs"
echo "=== F: assets gso_whey ==="
ls -laR "$REPO/assets/objects/gso_whey_protein_vanilla"
echo "=== G: outcomes ==="
ls -la "$WS/outcomes" 2>/dev/null
echo "=== H: datasets/rolling ==="
ls -la "$WS/datasets/rolling" 2>/dev/null
ls -la "$WS/datasets/rolling/seed-001001" 2>/dev/null
echo "RC RECON DONE"
