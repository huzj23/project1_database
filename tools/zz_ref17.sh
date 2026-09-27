#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== runtime uses of bounding_radius / .radius / footprint_radius ==="
grep -rn "bounding_radius" "$R/src" "$R/tests" 2>/dev/null
echo
echo "=== where is asset.radius / asset.support_height consumed ==="
grep -rn "asset\.radius\|\.support_height\|asset\.collision\." "$R/src" 2>/dev/null | grep -v '\.pyc'
echo
echo "=== validation checks that touch radius ==="
grep -rn "radius" "$R/src/physim/validation/__init__.py" | head -40
