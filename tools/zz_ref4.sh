#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== configs/assets.yaml ==="
cat "$R/configs/assets.yaml"
echo "=== configs/server.yaml ==="
cat "$R/configs/server.yaml"
echo "=== grep old id across repo (excluding datasets) ==="
grep -rn "gso_sootheze_cold_therapy_elephant" "$R" --exclude-dir=datasets --exclude-dir=.git -l 2>/dev/null
echo "=== grep old id INSIDE datasets (report only) ==="
grep -rn "gso_sootheze_cold_therapy_elephant" "$R/datasets" -l 2>/dev/null
echo "=== grep scene.glb references ==="
grep -rn "scene\.glb" "$R" --exclude-dir=datasets --exclude-dir=.git 2>/dev/null | head -50
echo "=== grep scene.blend1 references ==="
grep -rn "scene\.blend1" "$R" --exclude-dir=datasets --exclude-dir=.git 2>/dev/null | head -20
echo "=== grep t3dev-bak references ==="
grep -rn "t3dev-bak" "$R" --exclude-dir=datasets --exclude-dir=.git 2>/dev/null | head -20
