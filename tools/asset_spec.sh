#!/usr/bin/env bash
# What does AssetSpec actually expose?  (support_height worked, footprint_radius did not.)
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== AssetSpec definition ==="
grep -n 'class AssetSpec' -A40 src/physim/assets/__init__.py | sed 's/^/  /'

echo
echo "=== what the elephant resolves to ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys, dataclasses
sys.path.insert(0, "src")
from physim.assets import AssetManager
am = AssetManager("configs/assets.yaml", "assets")
a = am.get("gso_sootheze_cold_therapy_elephant")
for f in dataclasses.fields(a):
    print(f"  {f.name} = {getattr(a, f.name)}")
PY

echo
echo "=== the radius field name used by the rolling scenario ==="
grep -rn '\.radius\b' src/physim/scenarios/*.py src/physim/maps/surface_sampler.py | head -12 | sed 's/^/  /'
