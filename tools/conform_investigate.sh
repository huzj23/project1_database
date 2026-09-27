#!/usr/bin/env bash
# ===========================================================================
# Investigate three conformance questions before uploading:
#
#  A. "把所有东西都设为被动项" -- do the MENTOR'S OWN object assets declare passive
#     physics (mass_range [0.0,0.0] / static), and how do ours compare?
#  B. The turntable payload includes stray backup files (*.nomtl-bak,
#     asset.yaml.pre_lic) that must not be published.
#  C. The turntable declares visual.material pbr=dark_wood, but the PBR texture root
#     resolves to the WORKSPACE models/pbr_textures -- OUTSIDE the asset directory.
#     If so, a fresh clone + download would not have the textures, so the asset would
#     not actually be usable.  Determine the truth.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== A. passive-physics convention across ALL asset manifests ==="
"$PY" - <<'PY'
import glob, yaml
rows = []
for p in sorted(glob.glob("assets/*/*/asset.yaml")):
    m = yaml.safe_load(open(p)) or {}
    ph = m.get("physics") or {}
    rows.append((str(m.get("id")), str(m.get("kind")), str(m.get("category")),
                 ph.get("mass_range"), ph.get("static")))
print(f"  {'id':44s} {'kind':12s} {'mass_range':22s} static")
for i, k, c, mr, st in rows:
    print(f"  {i:44s} {k:12s} {str(mr):22s} {st}")
PY

echo
echo "=== A2. full physics block of the mentor's own objects vs ours ==="
for f in assets/objects/sphere_baseball/asset.yaml assets/objects/food_lime/asset.yaml \
         assets/objects/special_coffee_cup/asset.yaml \
         assets/objects/special_plush_elephant/asset.yaml; do
  echo "  --- $f ---"
  "$PY" -c "
import yaml,sys
m=yaml.safe_load(open('$f'))
print('    id=',m.get('id'),'kind=',m.get('kind'),'category=',m.get('category'))
print('    physics=',m.get('physics'))
print('    material_class=',m.get('material_class'))
print('    allowed_scenarios=',m.get('allowed_scenarios'))
" 2>&1
done

echo
echo "=== B. turntable stray files ==="
for f in assets/objects/turntable/visual/model.obj.nomtl-bak \
         assets/objects/turntable/visual/model.mtl.nomtl-bak \
         assets/objects/turntable/asset.yaml.pre_lic; do
  if [ -f "$f" ]; then
    base="${f%.nomtl-bak}"; base="${base%.pre_lic}"
    [ -f "$base" ] && echo "  $(basename $f): identical to $(basename $base)? $(cmp -s "$f" "$base" && echo YES || echo NO)"
    echo "     size=$(stat -c%s "$f")"
  fi
done

echo
echo "=== C. where does the turntable's PBR texture root actually resolve? ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.render.materials import resolve_pbr_root, find_texture_dir, DEFAULT_PBR_ROOT_RELPATH
r = resolve_pbr_root()
print('  PBR root            :', r)
print('  exists              :', r.is_dir())
d = find_texture_dir('dark_wood','wood_textures')
print('  dark_wood texture dir:', d)
import os
if d:
    for f in sorted(os.listdir(d)): print('     ', f)
" 2>&1 | sed 's/^/  /'

echo
echo "=== C2. is models/pbr_textures inside the git repo or the workspace? ==="
ls -d "$REPO/models" 2>/dev/null && echo "  repo has models/" || echo "  repo has NO models/ dir"
ls -d "$WS/models/pbr_textures" 2>/dev/null && echo "  workspace models/pbr_textures EXISTS (outside the repo)"
du -sh "$WS/models/pbr_textures" 2>/dev/null | sed 's/^/  size: /'
find "$WS/models/pbr_textures" -name '*dark_wood*' | head -8 | sed 's/^/  /'

echo
echo "=== C3. repo .gitignore (which paths are Git vs HF) ==="
cat .gitignore 2>/dev/null | head -40 | sed 's/^/  /'

echo
echo "=== C4. does the turntable asset carry its own texture fallback? ==="
ls -la assets/objects/turntable/visual/ | sed 's/^/  /'
echo "  --- visual/model.mtl ---"
cat assets/objects/turntable/visual/model.mtl | sed 's/^/  /'
