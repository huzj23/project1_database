#!/usr/bin/env bash
# ===========================================================================
# Can the turntable be made SELF-CONTAINED?
#
# The turntable declares `visual.material: {pbr: dark_wood}`, which materials.py
# resolves against the shared library at <workspace>/models/pbr_textures (623 MB,
# deliberately OUTSIDE the repo).  A fresh clone + HF download therefore would NOT
# have those textures, so the asset would raise FileNotFoundError and be unusable --
# which contradicts the user's "确保其可用" requirement.
#
# Read the rest of materials.py to see the exact search order, and size the three
# dark_wood 4k maps to judge whether shipping them inside the asset is practical.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== materials.py lines 80-200 ==="
sed -n '80,200p' src/physim/render/materials.py | cat -n | sed 's/^/  /' | sed 's/^  \([ 0-9]*\)/  L\1/'

echo
echo "=== how the renderer calls it (asset directory available?) ==="
grep -n 'apply_declared_material\|declared_materials\|support_material' src/physim/render/blender_backend.py | sed 's/^/  /'
sed -n '/apply_declared_material/,+18p' src/physim/render/blender_backend.py | head -50 | sed 's/^/  /'

echo
echo "=== size of the dark_wood 4k map set ==="
D="$WS/models/pbr_textures/wood_textures/dark_wood.blend/textures"
ls -la "$D" | sed 's/^/  /'
du -sh "$D" | sed 's/^/  TOTAL: /'
