#!/usr/bin/env bash
echo "=== WS tools preflight_full3.sh ==="
ls -la /data/raw/huzijian/project1_database/tools/preflight_full3.sh
echo "=== find preflight scripts ==="
find /data/raw/huzijian/project1_database -maxdepth 3 -name 'preflight_full3.sh' -printf '%p %s\n' 2>/dev/null
echo "=== repo root ==="
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
ls -la "$R"
echo "=== configs ==="
ls -la "$R/configs/"
echo "=== configs/scenarios ==="
ls -la "$R/configs/scenarios/"
echo "=== maps.yaml ==="
cat "$R/configs/maps.yaml"
