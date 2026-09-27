#!/usr/bin/env bash
# RECON for the two user requests:
#   (1) ONE more 匀速 clip: new camera angle + a PLAUSIBLE object.  A can sliding on
#       the floor unmotivated is the complaint -- I need to know which real objects
#       can legitimately ROLL (i.e. are round) and what the scene offers.
#   (2) turntable #5/#6 with the previously-approved camera pose and the ELEPHANT.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== is my friction change actually on the server? ==="
grep -n 'base_physics' src/physim/scenarios/rolling.py src/physim/scenarios/constant_force.py src/physim/scenarios/free_fall.py | sed 's/^/  /'
echo "  --- common.base_physics signature ---"
grep -n 'def base_physics' -A18 src/physim/scenarios/common.py | sed 's/^/  /'

echo
echo "=== all object assets: shape + dimensions + visual presence ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import os, yaml, glob
base = "assets/objects"
for d in sorted(glob.glob(base + "/*")):
    aid = os.path.basename(d)
    ay = os.path.join(d, "asset.yaml")
    if not os.path.isfile(ay):
        continue
    a = yaml.safe_load(open(ay)) or {}
    vis = os.path.isfile(os.path.join(d, "visual/model.obj")) or \
          os.path.isfile(os.path.join(d, "visual/model.glb"))
    dims = a.get("dimensions") or a.get("size") or a.get("extent")
    print(f"  {aid:46s} cat={str(a.get('category')):10s} vis={vis} "
          f"r={a.get('radius')} sh={a.get('support_height')} dims={dims}")
PY

echo
echo "=== GSO object manifest details (mass + friction + dims) ==="
for f in assets/objects/gso_*/asset.yaml; do
  echo "--- $(basename $(dirname $f)) ---"
  grep -nE 'category|radius|support_height|footprint|mass_range|friction_range|dimensions|allowed_scenarios|initial_quaternion' "$f" | sed 's/^/    /'
done

echo
echo "=== does the map declare a camera override for table_top? ==="
grep -n 'table_top' -A22 configs/maps.yaml | grep -nE 'camera|position|look|focal|region_id|bounds' | sed 's/^/  /'

echo
echo "=== approved turntable camera, recomputed from the frozen table values ==="
"$WS/tools/conda_env/bin/python" -c "
TX, TY, TZ = 0.414, 0.175, 0.7584
print(f'  table top      = ({TX}, {TY}, {TZ})')
print(f'  approved cam   = ({TX+0.52:.4f}, {TY-0.66:.4f}, {TZ+0.42:.4f})')
print(f'  approved look  = ({TX}, {TY}, {TZ+0.05:.4f})')
print(f'  focal          = 50.0 mm, sensor 36.0')
import math
d = math.dist((TX+0.52, TY-0.66, TZ+0.42), (TX, TY, TZ+0.05))
print(f'  distance       = {d:.4f} m')
print(f'  elevation      = {math.degrees(math.asin((0.42-0.05)/d)):.2f} deg')
"
