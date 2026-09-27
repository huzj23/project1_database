#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== grep footprint_radius in repo ==="
grep -rn "footprint_radius" "$R/src" "$R/scripts" "$R/tests" "$R/docs" 2>/dev/null
echo "=== turntable asset.yaml ==="
cat "$R/assets/objects/turntable/asset.yaml" 2>/dev/null
echo "=== turntable tree ==="
find "$R/assets/objects/turntable" -printf '%y %10s %p\n' | sort -k3
echo "=== all asset.yaml ids ==="
find "$R/assets" -name asset.yaml | sort | while read f; do printf '%s -> ' "$f"; grep -m1 '^id:' "$f"; done
