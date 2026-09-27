#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
D="$R/datasets/turntable_carry/seed-005001/x1"
mkdir -p "$R/../_zzframes"
cp "$D/rgb/rgb_00000.png" /data/raw/huzijian/project1_database/tmp/zz_tt_00000.png
cp "$D/rgb/rgb_00040.png" /data/raw/huzijian/project1_database/tmp/zz_tt_00040.png 2>/dev/null
ls -la /data/raw/huzijian/project1_database/tmp/zz_tt_*.png
echo "=== physics trajectory head (turntable_carry seed 5001) ==="
head -c 900 "$D/physics_trajectory.json" 2>/dev/null || ls "$D"
