#!/usr/bin/env bash
# Restore maps.yaml from backup and change ONLY the two value lines, preserving
# whatever indentation they already have.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
MAPS="$REPO/configs/maps.yaml"

cp "$WS/tmp/maps.bak" "$MAPS"
echo "  restored from backup"

"$WS/tools/conda_env/bin/python" - "$MAPS" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
out, in_region = [], False
changed = []
for ln in lines:
    if "region_id: replicad_apartment_floor_pinned" in ln:
        in_region = True
        out.append(ln)
        continue
    if in_region:
        stripped = ln.strip()
        if stripped.startswith("verification:"):
            ind = ln[:len(ln) - len(ln.lstrip())]
            out.append(ind + "verification: raycast_grid_0p10m_min_clearance_3p40m")
            changed.append("verification")
            continue
        if stripped.startswith("bounds_xy:"):
            ind = ln[:len(ln) - len(ln.lstrip())]
            out.append(ind + "bounds_xy: [-1.6000, 3.6000, -6.8000, -1.8000]")
            changed.append("bounds_xy")
            in_region = False
            continue
    out.append(ln)
open(p, "w").write("\n".join(out))
print("  changed:", changed)
PY

echo
echo "=== region ==="
grep -A6 'replicad_apartment_floor_pinned' "$MAPS" | cat -A | sed 's/\$$//' | sed 's/^/  /'
echo
echo "=== yaml validation ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
d = yaml.safe_load(open('$MAPS')); print('  maps.yaml OK')
a = yaml.safe_load(open('$REPO/assets/environments/replicad_apartment/asset.yaml')); print('  asset.yaml OK')
print('  collision:', a['collision'])
def walk(x):
    if isinstance(x, dict):
        if x.get('region_id') == 'replicad_apartment_floor_pinned': yield x
        for v in x.values(): yield from walk(v)
    elif isinstance(x, list):
        for v in x: yield from walk(v)
for r in walk(d):
    print('  region:', {k: r.get(k) for k in ('region_id','position','bounds_xy','verification')})
" 2>&1 | sed 's/^/  /'
