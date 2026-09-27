#!/usr/bin/env bash
# The DatasetWriter zero-pads the seed (seed-001001), so monitor THAT path.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== seed-001001 contents ==="
D="$REPO/datasets/rolling/seed-001001/x1"
for sub in rgb depth segmentation; do
  echo "  $sub: $(ls $D/$sub 2>/dev/null | wc -l)"
done
ls -la "$D" 2>/dev/null | sed 's/^/  /'

echo
echo "=== mp4 + metadata ==="
ls -la "$D"/*.mp4 "$D"/*.json 2>/dev/null | sed 's/^/  /'

echo
echo "=== validation ==="
[ -f "$D/metadata.json" ] && "$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('$D/metadata.json')); v=m.get('validation',{})
print('  valid=',v.get('valid'),' reasons=',v.get('reasons'))
mt=v.get('metrics',{})
for k in ('travel_distance','supported_fraction','max_speed_relative_change','trajectory_extent_object_ratio'):
    print('   ',k,'=',mt.get(k))
" 2>&1 | sed 's/^/  /'

echo
echo "=== all seed dirs ==="
ls -d "$REPO"/datasets/*/seed-*/x1 2>/dev/null | sed 's/^/  /'
