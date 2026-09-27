#!/usr/bin/env bash
# Deploy check + the whey-can geometry needed to make it ROLL ON ITS SIDE.
#
# Why this matters: the user rejected "a can sliding at constant velocity on the
# floor" as physically unmotivated.  The whey can is the ONLY near-circular asset
# we own (measured r_cv=0.078, roll_wobble=0.0048), so laid on its side it can
# genuinely ROLL -- and then constant velocity needs no explanation at all.
# For rolling without slipping the spin axis is horizontal and the support height
# is the CROSS-SECTION RADIUS, not the upright support_height.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== fixed camera policy smoke test ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.camera import fixed_camera
from physim.physics import SimulationResult
r = SimulationResult(trajectory=())
c = fixed_camera(r, {"position": (0.72, -0.46, 1.1784),
                     "look_at": (0.2, 0.2, 0.8084),
                     "focal_length_mm": 50.0})
print("  FIXEDCAM", c.position, c.look_at, c.focal_length_mm)
print("  distance", round(c.framing["distance"], 4), "mode", c.framing["mode"])
try:
    fixed_camera(r, {"position": (1, 1, 1), "look_at": (1, 1, 1), "focal_length_mm": 50.0})
    print("  ERROR: identical position/look_at was accepted")
except ValueError as e:
    print("  guard ok:", e)
PY

echo
echo "=== full whey_protein_vanilla asset.yaml ==="
cat assets/objects/gso_whey_protein_vanilla/asset.yaml | sed 's/^/  /'

echo
echo "=== whey collision urdf ==="
cat assets/objects/gso_whey_protein_vanilla/collision/model.urdf | sed 's/^/  /'

echo
echo "=== is there any orientation override support in the rolling scenario? ==="
grep -rn 'initial_quaternion\|orientation' src/physim/scenarios/*.py src/physim/assets/__init__.py | sed 's/^/  /'

echo
echo "=== AssetSpec fields ==="
grep -n 'class AssetSpec' -A30 src/physim/assets/__init__.py | sed 's/^/  /'
