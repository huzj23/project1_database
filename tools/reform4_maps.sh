#!/usr/bin/env bash
# Fix the maps.yaml region widening (the previous regex missed because of the
# long `verification:` line).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
MAPS="$REPO/configs/maps.yaml"

"$WS/tools/conda_env/bin/python" - "$MAPS" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
out, i, done = [], 0, False
while i < len(lines):
    out.append(lines[i])
    if "region_id: replicad_apartment_floor_pinned" in lines[i]:
        # replace the next 5 lines (verification, position, normal, bounds_xy)
        j = i + 1
        # keep cleanliness line
        if j < len(lines) and "cleanliness:" in lines[j]:
            out.append(lines[j]); j += 1
        out.append("              # Widened from the old 1.7 x 1.7 m pin.  Collision now uses")
        out.append("              # the scene's full 94 m^2 floor, so this only bounds where")
        out.append("              # the actor is PLACED -- it still stays in the open living area.")
        out.append("              verification: raycast_grid_0p10m_min_clearance_3p40m")
        out.append("              position: [1.0000, -4.3000, 0.0007]")
        out.append("              normal: [0.0, 0.0, 1.0]")
        out.append("              bounds_xy: [-1.6000, 3.6000, -6.8000, -1.8000]")
        # skip the old lines up to and including the old bounds_xy
        while j < len(lines) and "bounds_xy:" not in lines[j]:
            j += 1
        j += 1
        i = j
        done = True
        continue
    i += 1
open(p, "w").write("\n".join(out))
print("  maps.yaml updated:", done)
PY

echo
echo "=== resulting region ==="
grep -A10 'replicad_apartment_floor_pinned' "$MAPS" | sed 's/^/  /'

echo
echo "=== yaml still valid? ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
d = yaml.safe_load(open('$MAPS'))
print('  maps.yaml parses OK, top-level keys:', list(d.keys())[:6])
a = yaml.safe_load(open('$REPO/assets/environments/replicad_apartment/asset.yaml'))
print('  asset.yaml parses OK')
print('  collision:', a['collision'])
" 2>&1 | sed 's/^/  /'
