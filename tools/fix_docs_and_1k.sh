#!/usr/bin/env bash
# ===========================================================================
# 1. Correct validation entry point (validate_simulation does not exist).
# 2. Decide the fate of the unreferenced dark_wood_diff_1k.jpg.
# 3. Update the docstrings that document `visual.material`.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. validation public API ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
import physim.validation as v
print('  exports:', [n for n in dir(v) if not n.startswith('_')])
" 2>&1 | sed 's/^/  /'
echo "  --- how do the other tools validate? ---"
grep -rn 'validate\|valid' "$WS/tools/preflight_full3.sh" 2>/dev/null | head -6 | sed 's/^/  /'

echo
echo "=== 2. is dark_wood_diff_1k.jpg referenced ANYWHERE? ==="
grep -rn 'diff_1k' --include='*.py' --include='*.yaml' --include='*.mtl' --include='*.obj' --include='*.md' . 2>/dev/null | grep -v '^./datasets' | sed 's/^/  /' || echo "  UNREFERENCED -> dead weight, move it out"

echo
echo "=== 3. docstring updates for the new `textures` field ==="
"$PY" - <<'PY'
import pathlib

# 3a. MaterialSpec docstring example
p = pathlib.Path("src/physim/assets/__init__.py")
t = p.read_text(encoding="utf-8")
old = """            pbr: dark_wood          # Poly Haven set, i.e. <pbr>.blend/textures
            category: wood_textures # sub-directory of the PBR texture root
            uv_scale: 1.6           # uniform scale on the texture mapping node

    ``category`` may be omitted, in which case every category under the texture
    root is searched.  ``uv_scale`` defaults to 1.0, i.e. the mesh's own UVs."""
new = """            pbr: dark_wood          # Poly Haven set, i.e. <pbr>.blend/textures
            category: wood_textures # sub-directory of the PBR texture root
            uv_scale: 1.6           # uniform scale on the texture mapping node
            textures: visual/textures/dark_wood  # optional asset-local maps

    ``category`` may be omitted, in which case every category under the texture
    root is searched.  ``uv_scale`` defaults to 1.0, i.e. the mesh's own UVs.

    ``textures`` is optional and names a directory RELATIVE TO THE ASSET that holds
    the maps.  When present it is searched before the shared library, which lets an
    asset ship its own material and stay usable after
    ``sync_hf_assets.py download`` on a machine that has no
    ``<workspace>/models/pbr_textures``."""
if "optional asset-local maps" in t:
    print("  3a MaterialSpec docstring already updated")
else:
    assert t.count(old) == 1, f"MaterialSpec docstring not unique ({t.count(old)})"
    p.write_text(t.replace(old, new), encoding="utf-8")
    print("  3a MaterialSpec docstring updated")

# 3b. materials.py module docstring
p2 = pathlib.Path("src/physim/render/materials.py")
t2 = p2.read_text(encoding="utf-8")
old2 = """    visual:
      mesh: visual/model.obj
      material:
        pbr: dark_wood
        category: wood_textures
        uv_scale: 1.6
"""
new2 = """    visual:
      mesh: visual/model.obj
      material:
        pbr: dark_wood
        category: wood_textures
        uv_scale: 1.6
        textures: visual/textures/dark_wood   # optional, asset-local

Lookup order for the maps is: the asset-local ``textures`` directory first (so an
asset can carry its own material and remain usable after an HF download), then the
shared library at ``<workspace>/models/pbr_textures``.
"""
if "asset-local ``textures`` directory first" in t2:
    print("  3b materials.py docstring already updated")
else:
    assert t2.count(old2) == 1, f"materials docstring not unique ({t2.count(old2)})"
    p2.write_text(t2.replace(old2, new2), encoding="utf-8")
    print("  3b materials.py docstring updated")
PY

echo
echo "=== 4. move the unreferenced 1k map out of the asset ==="
STRAY="$WS/tmp/strays"
mkdir -p "$STRAY/assets/objects/turntable/visual/textures"
if [ -f assets/objects/turntable/visual/textures/dark_wood_diff_1k.jpg ]; then
  mv assets/objects/turntable/visual/textures/dark_wood_diff_1k.jpg \
     "$STRAY/assets/objects/turntable/visual/textures/"
  echo "  moved dark_wood_diff_1k.jpg -> tmp/strays (unreferenced dead weight)"
fi
ls -la assets/objects/turntable/visual/textures/ | sed 's/^/  /'
ls -la assets/objects/turntable/visual/textures/dark_wood/ | sed 's/^/  /'
