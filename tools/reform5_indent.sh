#!/usr/bin/env bash
# Fix the indentation on the widened region (my inserted lines were 2 spaces too
# deep, which broke the YAML).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
MAPS="$REPO/configs/maps.yaml"

"$WS/tools/conda_env/bin/python" - "$MAPS" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
out = []
for ln in lines:
    # the region's children must sit at 14 spaces, same as `cleanliness:`
    if ln.startswith("                # Widened") or \
       ln.startswith("                # the scene") or \
       ln.startswith("                # the actor") or \
       ln.startswith("                verification:") or \
       ln.startswith("                position: [1.0000, -4.3000") or \
       ln.startswith("                normal: [0.0, 0.0, 1.0]") or \
       ln.startswith("                bounds_xy: [-1.6000"):
        out.append("              " + ln.strip())
    else:
        out.append(ln)
open(p, "w").write("\n".join(out))
print("  reindented")
PY

echo "=== region now ==="
grep -A10 'replicad_apartment_floor_pinned' "$MAPS" | sed 's/^/  /'
echo
echo "=== yaml validation ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
d = yaml.safe_load(open('$MAPS'))
print('  maps.yaml OK')
a = yaml.safe_load(open('$REPO/assets/environments/replicad_apartment/asset.yaml'))
print('  asset.yaml OK')
print('  collision:', a['collision'])
# confirm the region landed
def walk(x):
    if isinstance(x, dict):
        if x.get('region_id') == 'replicad_apartment_floor_pinned':
            yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)
for r in walk(d):
    print('  region:', {k: r[k] for k in ('region_id','position','bounds_xy') if k in r})
" 2>&1 | sed 's/^/  /'
