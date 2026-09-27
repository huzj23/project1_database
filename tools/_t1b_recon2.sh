#!/usr/bin/env bash
# Recon 2: datasets, environment asset manifest, maps render block.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== A: repo datasets ==="
ls -la "$REPO/datasets" 2>/dev/null
echo "--- rolling ---"
ls -la "$REPO/datasets/rolling" 2>/dev/null
echo "--- seed-001001 ---"
ls -la "$REPO/datasets/rolling/seed-001001" 2>/dev/null
echo "--- x1 ---"
ls -la "$REPO/datasets/rolling/seed-001001/x1" 2>/dev/null
echo "=== B: assets.yaml ==="
cat "$REPO/configs/assets.yaml"
echo "=== C: env asset dir ==="
ls -la "$REPO/assets/environments" 2>/dev/null
ls -la "$REPO/assets/environments/replicad_apartment" 2>/dev/null
echo "=== D: env asset.yaml ==="
cat "$REPO/assets/environments/replicad_apartment/asset.yaml" 2>/dev/null
echo "=== E: metadata camera (existing clip) ==="
"$WS/tools/conda_env/bin/python" -c "
import json
p='$REPO/datasets/rolling/seed-001001/x1/metadata.json'
d=json.load(open(p))
print('camera', json.dumps(d.get('camera'), indent=1)[:1200])
print('physics keys', list(d.get('physics',{}).keys()))
ph=d['physics']
for k in ('position','linear_velocity','angular_velocity','support_height','radius','initial_quaternion','surface_id','friction','mass'):
    print(' ph', k, ph.get(k))
print('validation', json.dumps(d.get('validation'), indent=1)[:1500])
print('frame_count', d.get('frame_count'), 'modalities', d.get('modalities'))
"
echo "RC RECON2 DONE"
