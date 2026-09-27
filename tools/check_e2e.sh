#!/usr/bin/env bash
# Proof that the pipeline actually runs end-to-end, and what it produced.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== existing dataset outputs ==="
find "$REPO/datasets" -maxdepth 3 -type d 2>/dev/null | head -20 | sed "s|$REPO/|  |"

echo
echo "=== one sample's contents ==="
d=$(find "$REPO/datasets" -maxdepth 3 -type d -name 'x*' 2>/dev/null | head -1)
echo "  sample: ${d#$REPO/}"
ls -la "$d" 2>/dev/null | tail -20 | sed 's/^/    /'

echo
echo "=== metadata.json of that sample (the acceptance record) ==="
"$WS/tools/conda_env/bin/python" -c "
import json,glob,os
f=glob.glob('$d/metadata.json')
if f:
    m=json.load(open(f[0]))
    print(json.dumps(m,indent=2)[:2000])
else:
    print('  no metadata.json')
" 2>&1 | sed 's/^/  /'

echo
echo "=== server.yaml (full) ==="
cat "$REPO/configs/server.yaml" 2>/dev/null | sed 's/^/  /'
