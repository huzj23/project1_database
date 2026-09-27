#!/usr/bin/env bash
# ===========================================================================
# What does the AssetManager actually ENFORCE, and how does the local GUI preview
# work?  Both matter for making our assets conformant and for showing the user a
# Blender preview before uploading.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== category constants + validation in assets/__init__.py ==="
grep -n 'CATEGOR\|ASSET_KINDS\|category\|PRIMITIVE\|convex_hull\|bounding_radius\|support_height\|footprint_radius\|raise ' \
  src/physim/assets/__init__.py | head -50 | sed 's/^/  /'

echo
echo "=== preview scripts: what do they do / how invoked ==="
head -40 scripts/preview_blender.py | sed 's/^/  /'
echo "  ---------------- blender_preview_scene.py ----------------"
head -30 scripts/blender_preview_scene.py | sed 's/^/  /'

echo
echo "=== preview entry points in the README ==="
grep -n 'preview' README.md | head -20 | sed 's/^/  /'

echo
echo "=== configs available ==="
ls configs/*.yaml | sed 's/^/  /'
echo "  --- local.user.yaml? ---"
ls configs/local*.yaml 2>/dev/null | sed 's/^/  /' || echo "  none"
