#!/usr/bin/env bash
V=/data/raw/huzijian/project1_database/code/vendor/phyco-sim
echo "=== blender.py 596-625 ==="
sed -n '596,625p' "$V/kubric/kubric/renderer/blender.py"
echo "=== blender.py 1195-1215 ==="
sed -n '1195,1215p' "$V/kubric/kubric/renderer/blender.py"
echo "=== depth2 ==="
/data/raw/huzijian/project1_database/tools/conda_env/bin/python \
  /data/raw/huzijian/project1_database/tools/zz_depth2.py 2>&1
