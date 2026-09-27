#!/usr/bin/env bash
# ===========================================================================
# Verify the asset-local material patch, and clean stray backup files.
#
# The decisive test: hide the SHARED texture library and confirm the turntable still
# resolves dark_wood from inside the asset.  That is exactly the situation a teammate
# is in after `git clone` + `sync_hf_assets.py download`.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. syntax check both patched files ==="
"$PY" -m py_compile src/physim/assets/__init__.py src/physim/render/materials.py && echo "  both compile OK"

echo
echo "=== 2. AssetManager parses the new fields ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.assets import AssetManager
am = AssetManager('configs/assets.yaml','assets')
t = am.get('turntable')
print('  turntable.material =', t.material)
e = am.get('special_plush_elephant')
print('  elephant.material  =', e.material)
print('  total assets       =', len(am.ids))
" 2>&1 | sed 's/^/  /'

echo
echo "=== 3. resolve with the SHARED library present (normal case) ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.render.materials import find_texture_dir
from physim.assets import AssetManager
am = AssetManager('configs/assets.yaml','assets')
t = am.get('turntable')
d = find_texture_dir('third_party/phyco-sim', 'dark_wood', 'wood_textures', t.material)
print('  resolved ->', d)
import os; print('  files:', sorted(os.listdir(d)))
" 2>&1 | sed 's/^/  /'

echo
echo "=== 4. DECISIVE: hide the shared library, resolve again ==="
SHARED="$WS/models/pbr_textures"
HIDDEN="$WS/tmp/pbr_textures_hidden"
rm -rf "$HIDDEN"; mv "$SHARED" "$HIDDEN"
echo "  moved shared library away: $SHARED -> $HIDDEN"
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.render.materials import find_texture_dir, resolve_pbr_root
from physim.assets import AssetManager
am = AssetManager('configs/assets.yaml','assets')
print('  shared root now exists:', resolve_pbr_root('third_party/phyco-sim').is_dir())
t = am.get('turntable')
d = find_texture_dir('third_party/phyco-sim', 'dark_wood', 'wood_textures', t.material)
print('  turntable resolved ->', d)
import os
if d: print('  files:', sorted(os.listdir(d)))
# an asset WITHOUT an asset-local dir must now fail loudly (unchanged behaviour)
from physim.render.materials import apply_declared_material
print('  elephant has no declared material:', am.get('special_plush_elephant').material is None)
" 2>&1 | sed 's/^/  /'

echo
echo "=== 5. restore the shared library ==="
mv "$HIDDEN" "$SHARED"
echo "  restored: $SHARED exists = $([ -d "$SHARED" ] && echo YES || echo NO)"

echo
echo "=== 6. clean stray backup files out of assets/ (move, never delete) ==="
STRAY="$WS/tmp/strays"; mkdir -p "$STRAY"
n=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  rel="${f#$REPO/}"
  mkdir -p "$STRAY/$(dirname "$rel")"
  mv "$f" "$STRAY/$rel"
  echo "  moved $rel"
  n=$((n+1))
done < <(find assets -type f \( -name '*.t3dev-bak' -o -name '*.nomtl-bak' -o -name '*.pre_lic' -o -name '*.pre_scen' -o -name '*.pre_localtex' \) 2>/dev/null)
echo "  total moved: $n"

echo
echo "=== 7. assets/ is now free of strays ==="
find assets -type f \( -name '*bak*' -o -name '*.pre_*' \) 2>/dev/null | sed 's/^/  /' || true
echo "  (nothing above = clean)"

echo
echo "=== 8. preflight ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -3 | sed 's/^/  /'
