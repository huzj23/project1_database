#!/usr/bin/env bash
# Check the material-hook subagent's real progress on the server.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== render module files ==="
ls -la src/physim/render/ | sed 's/^/  /'
echo "=== assets module ==="
ls -la src/physim/assets/ | sed 's/^/  /'
echo
echo "=== any material hook yet? ==="
grep -rn 'pbr\|material_root\|PBR' src/physim/render/*.py src/physim/assets/__init__.py 2>/dev/null | head -20 | sed 's/^/  /'
echo
echo "=== turntable asset.yaml (material declared?) ==="
cat assets/objects/turntable/asset.yaml | sed 's/^/  /'
echo
echo "=== files changed in last 60 min ==="
find src assets configs scripts -newermt '-60 minutes' -type f 2>/dev/null | grep -v __pycache__ | sed 's/^/  /'
echo
echo "=== any probe/mat logs from the subagent ==="
ls -lat "$WS/tmp"/*.log 2>/dev/null | head -8 | sed 's/^/  /'
echo
echo "=== running processes ==="
pgrep -af 'python|blender' 2>/dev/null | grep -viE 'grep|pgrep|ssh_ctl' | head -6 | sed 's/^/  /'
