#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
W=/data/raw/huzijian/project1_database
echo "=== grep 0.202186 anywhere in workspace (tmp/tools/logs/code) ==="
grep -rn "0.202186" "$W/tools" "$W/tmp" "$W/log" "$R" 2>/dev/null | grep -v Binary | head -30
echo
echo "=== grep 1968 ==="
grep -rn "1968" "$W/tools" "$R/scripts" "$R/assets" 2>/dev/null | grep -v Binary | head -20
echo
echo "=== grep footprint_radius in tools ==="
grep -rln "footprint_radius" "$W/tools" 2>/dev/null | head -20
echo
echo "=== ls tmp (top level) ==="
ls -la "$W/tmp" | head -60
