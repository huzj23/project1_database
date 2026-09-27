#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== pipeline 198-225 (camera construction) ==="
sed -n '198,225p' "$R/src/physim/pipeline.py"
echo "=== pipeline _camera_config 93-126 ==="
sed -n '93,126p' "$R/src/physim/pipeline.py"
