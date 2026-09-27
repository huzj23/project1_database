#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== turntable_carry_gso.yaml ==="
cat -n "$R/configs/scenarios/turntable_carry_gso.yaml"
echo "=== turntable_spin_gso.yaml ==="
cat -n "$R/configs/scenarios/turntable_spin_gso.yaml"
echo "=== src tree ==="
find "$R/src" -name '*.py' -printf '%p\n' | sort
