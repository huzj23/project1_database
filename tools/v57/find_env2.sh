#!/bin/bash
# Locate the interpreter that produced the previous round's chain.log, by finding any pybullet compiled
# extension on the filesystem and reporting the python that owns it. Written as a file so quoting survives.
echo "=== pybullet extension modules ==="
find / -maxdepth 9 -name 'pybullet*.so' 2>/dev/null | head -20
echo "=== python binaries near those ==="
for so in $(find / -maxdepth 9 -name 'pybullet*.so' 2>/dev/null | head -5); do
    env_dir=$(echo "$so" | sed 's|/lib/python[^/]*/site-packages/.*||')
    echo "so=$so"
    echo "  owner=$env_dir"
    ls "$env_dir/bin/python"* 2>/dev/null
done
echo "=== conda env list ==="
/data/raw/wangzile/miniconda3/bin/conda env list 2>/dev/null
echo "=== any venv with pybullet in workspace ==="
find /data/raw/huzijian/project1_database -maxdepth 5 -name 'pyvenv.cfg' 2>/dev/null | head
echo "=== tmux sessions that ran the old job ==="
tmux ls 2>/dev/null | grep -iE 'b2|chain|domino|v56' | head
