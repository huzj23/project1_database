#!/bin/bash
# Find how the PREVIOUS round actually ran the solver: locate any pybullet install and any run script.
# Written as a file so quoting does not have to survive PowerShell.
WS=/data/raw/huzijian/project1_database
echo "=== pybullet dirs anywhere ==="
find /data/raw/wangzile /data/raw/huzijian -maxdepth 6 -name 'pybullet*' 2>/dev/null | head -20
echo "=== venvs in workspace ==="
ls -d $WS/.venv $WS/venv $WS/env 2>/dev/null
echo "=== how the old run was launched (look for launcher scripts) ==="
ls $WS/tools/v56/*.sh 2>/dev/null | head
echo "=== old chain log head ==="
head -12 $WS/outcomes/v56/mixed_box_domino/20260929T142714/chain.log 2>/dev/null
echo "=== old run README/README-ish ==="
ls $WS/outcomes/v56/mixed_box_domino/20260929T142714/deliver/ 2>/dev/null | head -20
echo "=== conda envs full ==="
ls /data/raw/wangzile/miniconda3/envs/ 2>/dev/null
echo "=== pybullet via pip list on base ==="
/data/raw/wangzile/miniconda3/bin/python -m pip list 2>/dev/null | grep -i -E 'bullet|gym|numpy' | head
