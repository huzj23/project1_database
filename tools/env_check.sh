#!/usr/bin/env bash
# ===========================================================================
# Is "Asset 'replicad_apartment' has no collision support height" PRE-EXISTING?
# Environments are not actors, so it is expected -- but prove it is identical in the
# ORIGINAL tree so the upload is not blamed.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== same probe in the ORIGINAL tree ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.assets import AssetManager
am = AssetManager('configs/assets.yaml','assets')
for aid in ('replicad_apartment','turntable','special_plush_elephant'):
    a = am.get(aid)
    try:
        h = a.support_height
        print(f'  {aid}: support_height={h}')
    except Exception as e:
        print(f'  {aid}: {type(e).__name__}: {e}')
" 2>&1 | sed 's/^/  /'

echo
echo "=== do the MENTOR's environments behave the same way? ==="
"$PY" -c "
import yaml, glob
for p in sorted(glob.glob('assets/environments/*/asset.yaml')):
    m = yaml.safe_load(open(p))
    c = m.get('collision') or {}
    print(f\"  {m.get('id'):22s} collision.type={c.get('type')} support_height={c.get('support_height')} surfaces={list((c.get('surfaces') or {}).keys()) if isinstance(c.get('surfaces'),dict) else c.get('surfaces')}\")
" 2>&1 | sed 's/^/  /'

echo
echo "=== apartment collision block (full) ==="
"$PY" -c "
import yaml
m = yaml.safe_load(open('assets/environments/replicad_apartment/asset.yaml'))
print(yaml.dump({'collision': m.get('collision')}, sort_keys=False, allow_unicode=True))
" 2>&1 | sed 's/^/  /'
