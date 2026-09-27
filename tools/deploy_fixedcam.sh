#!/usr/bin/env bash
# Deploy + verify the new `fixed` camera policy.
#
# The user asked for the turntable clips to use "我之前通过的场景和相机位姿" -- the
# pose that was reviewed and approved in tools/tt_on_table.sh.  That pose is
# absolute:
#     cam  = table_top + (0.52, -0.66, +0.42)
#     look = table_top + (0, 0, +0.05),  focal 50 mm, sensor 36 mm
# With the frozen table top (0.414, 0.175, 0.7584) this is
#     cam  = (0.934, -0.485, 1.1784)
#     look = (0.414, 0.175, 0.8084)
# The `trajectory_side` policy cannot reproduce a reviewed pose (it derives the
# camera from each clip's own motion), so an explicit policy is required.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== smoke test: fixed_camera ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.camera import fixed_camera
from physim.physics import SimulationResult

r = SimulationResult(trajectory=(), collisions=())
APPROVED = {
    "policy": "fixed",
    "position": (0.934, -0.485, 1.1784),
    "look_at": (0.414, 0.175, 0.8084),
    "focal_length_mm": 50.0,
    "framing": {"sensor_width_mm": 36.0},
}
c = fixed_camera(r, APPROVED)
print("  position  ", tuple(round(v, 4) for v in c.position))
print("  look_at   ", tuple(round(v, 4) for v in c.look_at))
print("  focal     ", c.focal_length_mm)
print("  distance  ", round(c.framing["distance"], 4))
print("  mode      ", c.framing["mode"])

# the pose must NOT depend on the trajectory (that is the whole point)
class Fake:
    def __init__(self, p): self.position = p
r2 = SimulationResult(trajectory=(Fake((99.0, -99.0, 99.0)), Fake((-99.0, 99.0, -99.0))), collisions=())
c2 = fixed_camera(r2, APPROVED)
print("  trajectory-independent:", c.position == c2.position and c.look_at == c2.look_at)

for bad, why in (
    ({"position": (1, 1, 1), "look_at": (1, 1, 1), "focal_length_mm": 50.0}, "degenerate"),
    ({"position": (1, 1), "look_at": (0, 0, 0), "focal_length_mm": 50.0}, "2-vector"),
    ({"focal_length_mm": 50.0}, "missing keys"),
):
    try:
        fixed_camera(r, bad)
        print(f"  GUARD FAILED ({why})")
    except ValueError as e:
        print(f"  guard ok ({why}): {e}")
PY

echo
echo "=== policy accepted by _camera_config? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.pipeline import _camera_config
from physim.maps import MapManager
from physim.assets import AssetManager

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = {"camera": {"policy": "fixed", "position": (0.934, -0.485, 1.1784),
                  "look_at": (0.414, 0.175, 0.8084), "focal_length_mm": 50.0},
       "output": {"resolution": [1920, 1080]}}

class FakeSample:
    seed = 1
    surface_id = "replicad_apartment_table_top"

out = _camera_config(cfg, ms, FakeSample())
print("  policy:", out.get("policy"))
print("  position preserved:", out.get("position"))
print("  azimuth injected:", "azimuth_offset_degrees" in out, "(must be False for fixed)")
PY

echo
echo "=== existing policies still fine ==="
"$WS/tools/conda_env/bin/python" -c "
import sys; sys.path.insert(0,'src')
from physim.pipeline import _camera_config
print('  import ok')
" 2>&1 | tail -2

echo
echo "=== backward compat: preflight the 14 clips again ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -3
