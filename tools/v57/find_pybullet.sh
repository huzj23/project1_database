#!/bin/bash
# Locate a Python interpreter that can import pybullet, and report each candidate's version.
# Written as a file because this command's quoting does not survive being passed through PowerShell.
echo "=== candidate interpreters ==="
for p in /data/raw/wangzile/miniconda3/bin/python3 \
         /data/raw/wangzile/miniconda3/bin/python \
         /data/raw/wangzile/miniconda3/envs/*/bin/python \
         /usr/bin/python3 ; do
    [ -x "$p" ] || continue
    v=$("$p" -c 'import pybullet,sys;print(pybullet.getAPIVersion())' 2>&1 | tail -1)
    echo "$p -> $v"
done
echo "=== which python3 ==="
which -a python3
