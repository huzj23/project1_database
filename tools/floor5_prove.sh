#!/usr/bin/env bash
# ===========================================================================
# PROVE the patch floor is gone: run the pipeline and show which support body
# the simulator actually built, plus that the sample still validates.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

rm -rf datasets/free_fall/seed-009100
echo "=== running free_fall with the extracted floor mesh ==="
"$WS/tools/conda_env/bin/python" scripts/generate.py \
    --config configs/server.yaml --seed 9100 --variant x1 \
    > "$WS/tmp/floorrun.log" 2>&1
echo "  exit=$?"

echo
echo "=== did the simulator build a MESH or a BOX? ==="
grep -iE 'surface_collision|FileBasedObject|Cube|urdf|floor' "$WS/tmp/floorrun.log" | head -12 | sed 's/^/  /'

echo
echo "=== validation ==="
"$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('datasets/free_fall/seed-009100/x1/metadata.json'))
v=m.get('validation',{})
print('  valid =', v.get('valid'))
print('  reasons =', v.get('reasons'))
mt=v.get('metrics',{})
for k in ('max_surface_penetration','drop_distance','supported_fraction','collision_count','trajectory_extent_object_ratio'):
    print(f'  {k} = {mt.get(k)}')
print()
print('  sample surface_id =', m.get('sample',{}).get('surface_id'))
" 2>&1 | sed 's/^/  /'

echo
echo "=== error scan ==="
grep -iE 'error|traceback|assert' "$WS/tmp/floorrun.log" | head -5 | sed 's/^/  /'
echo "  (empty = clean)"
