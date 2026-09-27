#!/usr/bin/env bash
# ===========================================================================
# Can we build a GUI preview .blend for the user to inspect?
#
# preview_blender.py -> blender_preview_scene.py needs:
#   * src/physim/preview.py  (add_preview_guides)
#   * a sample_root holding trajectory.json + collisions.json + metadata.json
#   * configs/local.yaml with paths.blender_python_packages + preview.save_blend
#
# Build it on the SERVER with Blender 3.4.1 (the exact pipeline version) and then
# download the .blend, because the local Blender is 5.2.2 and a locally built scene
# would not be the same artifact.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== does src/physim/preview.py exist? ==="
ls -la src/physim/preview.py 2>/dev/null | sed 's/^/  /' || echo "  MISSING"
echo "  --- what does it provide? ---"
grep -n 'def \|PREVIEW' src/physim/preview.py 2>/dev/null | head -12 | sed 's/^/    /'

echo
echo "=== preview-relevant config keys in configs/server.yaml ==="
grep -nA6 '^preview:' configs/server.yaml | sed 's/^/  /'
echo "  --- paths block ---"
grep -nA10 '^paths:' configs/server.yaml | sed 's/^/  /'

echo
echo "=== is there a local.yaml / local.user.yaml? ==="
ls configs/*.yaml | sed 's/^/  /'

echo
echo "=== a turntable sample bundle we could preview ==="
for d in datasets/turntable_spin/seed-005002/x1 datasets/turntable_carry/seed-005001/x1; do
  echo "  --- $d ---"
  ls -la "$d" | grep -E 'trajectory|collisions|metadata' | awk '{printf "    %-28s %8.1f KB\n", $9, $5/1024}'
  "$WS/tools/conda_env/bin/python" -c "
import json
m = json.load(open('$d/metadata.json'))
print('      asset :', m['asset'].get('id') or m['asset'].get('asset_id'))
print('      map   :', m['map'].get('id') or m['map'].get('map_id'))
print('      camera:', {k: m['camera'].get(k) for k in ('position','look_at','focal_length_mm')})
" 2>&1
done

echo
echo "=== assets.yaml: how are assets registered? ==="
cat configs/assets.yaml | sed 's/^/  /'
