#!/usr/bin/env bash
# ===========================================================================
# Remaining pre-upload questions:
#
#  C (cont). resolve_pbr_root(project_root) -- what is project_root, and would a
#     FRESH CLONE + HF DOWNLOAD be able to resolve the turntable's declared
#     `visual.material: {pbr: dark_wood}`?  The textures live in the WORKSPACE
#     (623 MB, outside the repo), so this is a real usability question.
#  D. Full .gitignore -- which paths go to Git vs HF.
#  E. Turntable visual/model.mtl content + whether visual/textures/ is referenced.
#  F. Do the mentor's own assets declare visual.material at all?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== D. full .gitignore ==="
cat -n .gitignore | sed 's/^/  /'

echo
echo "=== E. turntable visual dir + MTL ==="
ls -la assets/objects/turntable/visual/ assets/objects/turntable/visual/textures/ 2>/dev/null | sed 's/^/  /'
echo "  --- model.mtl ---"
cat assets/objects/turntable/visual/model.mtl | sed 's/^/  | /'
echo "  --- first 6 lines of model.obj ---"
head -6 assets/objects/turntable/visual/model.obj | sed 's/^/  | /'
echo "  --- does the OBJ reference the MTL / texture? ---"
grep -n 'mtllib\|usemtl' assets/objects/turntable/visual/model.obj | head | sed 's/^/  /'

echo
echo "=== C (cont). materials.py resolution logic ==="
sed -n '1,80p' src/physim/render/materials.py | cat -n | sed 's/^/  /'

echo
echo "=== C2. what project_root do callers pass? ==="
grep -rn 'resolve_pbr_root\|project_root_for' src/ scripts/ | sed 's/^/  /'
