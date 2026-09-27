#!/usr/bin/env bash
# Recon 3: quaternion convention in vendored kubric + dataset asset ids.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== A: kubric Object.quaternion ==="
grep -n "quaternion" "$REPO/third_party/phyco-sim/kubric/kubric/core/objects.py" | head -60
echo "=== B: kubric get_position_and_rotation ==="
grep -n "def get_position_and_rotation" -A 20 "$REPO/third_party/phyco-sim/kubric/kubric/simulator/pybullet.py"
echo "=== C: dataset asset ids ==="
for d in "$REPO"/datasets/rolling/seed-*/*/; do
  echo "--- $d"
  "$WS/tools/conda_env/bin/python" -c "
import json,sys
try:
    m=json.load(open('$d/metadata.json'))
    print('  asset', m['asset']['id'], 'variant', m['variant']['variant_id'], 'cam', m['camera']['framing'].get('mode'), m['camera']['position'])
except Exception as e:
    print('  ERR', e)
"
done
echo "=== D: outcomes/_t1 ==="
ls -la "$WS/outcomes/_t1" 2>/dev/null
echo "=== E: root datasets ==="
ls -la "$WS/datasets" 2>/dev/null
echo "=== F: cache dir ==="
ls -la "$REPO/cache" 2>/dev/null
echo "RC RECON3 DONE"
