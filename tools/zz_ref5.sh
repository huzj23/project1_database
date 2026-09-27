#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== configs/assets.yaml ==="
cat "$R/configs/assets.yaml"
echo "=== configs/server.yaml ==="
cat "$R/configs/server.yaml"
echo "=== grep old id in configs+src+scripts+tests+assets+docs ==="
grep -rn "gso_sootheze_cold_therapy_elephant" "$R/configs" "$R/src" "$R/scripts" "$R/tests" "$R/assets" "$R/docs" 2>/dev/null
echo "=== grep old id at repo root files ==="
grep -n "gso_sootheze_cold_therapy_elephant" "$R"/*.md "$R"/*.toml 2>/dev/null
echo "=== grep scene.glb in configs/src/scripts ==="
grep -rn "scene\.glb" "$R/configs" "$R/src" "$R/scripts" "$R/tests" 2>/dev/null | head -30
echo "=== grep scene.blend1 ==="
grep -rn "scene\.blend1" "$R/configs" "$R/src" "$R/scripts" "$R/tests" "$R/assets" 2>/dev/null | head
echo "=== grep t3dev-bak ==="
grep -rn "t3dev-bak" "$R/configs" "$R/src" "$R/scripts" "$R/tests" "$R/assets" 2>/dev/null | head
echo "=== datasets refs (count per file) ==="
grep -rln "gso_sootheze_cold_therapy_elephant" "$R/datasets" 2>/dev/null | head -40
echo "=== done ==="
