#!/usr/bin/env bash
V=/data/raw/huzijian/project1_database/code/vendor/phyco-sim
echo "=== blender.py around 550-575 ==="
sed -n '548,575p' "$V/kubric/kubric/renderer/blender.py"
echo "=== blender.py around 848-872 ==="
sed -n '846,872p' "$V/kubric/kubric/renderer/blender.py"
