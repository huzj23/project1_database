#!/usr/bin/env bash
# Check the material-hook subagent's progress and re-run the preflight.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== render module ==="
ls -la src/physim/render/ | sed 's/^/  /'
echo "=== turntable asset.yaml visual block ==="
sed -n '/^visual:/,/^visual_transform:/p' assets/objects/turntable/asset.yaml | sed 's/^/  /'
echo "=== material references in pipeline source ==="
grep -rn 'material' src/physim/assets/__init__.py src/physim/render/blender_backend.py 2>/dev/null | head -14 | sed 's/^/  /'
echo "=== asset restore state ==="
echo "  usemtl lines in model.obj: $(grep -c '^usemtl' assets/objects/turntable/visual/model.obj)"
echo "  model.mtl bytes: $(wc -c < assets/objects/turntable/visual/model.mtl)"
ls assets/objects/turntable/visual/ | sed 's/^/    /'
echo "=== recent file changes (last 40 min) ==="
find src assets configs -newermt '-40 minutes' -type f 2>/dev/null | grep -v __pycache__ | sed 's/^/  /'
