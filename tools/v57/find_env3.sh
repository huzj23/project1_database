#!/bin/bash
# Find the interpreter that owns a pybullet install, using only bounded searches so this cannot hang.
#
# A previous attempt used `find /` with a deep maxdepth and never returned; every search here is limited to
# specific directories and a modest depth.
echo "=== pip module search (fast, no filesystem walk) ==="
for p in /data/raw/wangzile/miniconda3/bin/python3 \
         /usr/bin/python3 \
         /data/raw/wangzile/miniconda3/envs/*/bin/python ; do
    [ -x "$p" ] || continue
    echo -n "$p : "
    "$p" -c 'import pybullet;print("pybullet",pybullet.getAPIVersion())' 2>&1 | tail -1
done

echo
echo "=== site-packages named pybullet, workspace + home only ==="
for root in /data/raw/wangzile /data/raw/huzijian /home/wangzile /root ; do
    [ -d "$root" ] || continue
    timeout 60 find "$root" -maxdepth 7 -name 'pybullet*' -print 2>/dev/null | head -10
done

echo
echo "=== conda env list ==="
timeout 60 /data/raw/wangzile/miniconda3/bin/conda env list 2>/dev/null

echo
echo "=== any python with a pybullet dist-info ==="
for root in /data/raw/wangzile/miniconda3 /data/raw/huzijian ; do
    timeout 60 find "$root" -maxdepth 8 -name 'pybullet-*.dist-info' -print 2>/dev/null | head -5
done
