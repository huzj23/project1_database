#!/usr/bin/env bash
# ===========================================================================
# Can the disc even CARRY a texture?  An OBJ needs UV coordinates for map_Kd.
#
# The disc was generated procedurally with an EMPTY model.mtl, so it has no
# material -- which is why it renders as default grey.  Before writing an MTL I
# must know whether the mesh has `vt` (UV) lines; without them the texture cannot
# be mapped and the MTL alone would do nothing.
#
# Also inspect the frozen dark_wood texture set and the exact helper that produced
# the measured R/B=1.83 result, so the asset can be rebuilt to match it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== disc OBJ: element counts ==="
OBJ=assets/objects/turntable/visual/model.obj
for k in v vt vn f o usemtl mtllib; do
  printf "  %-8s %s\n" "$k" "$(grep -c "^$k " $OBJ 2>/dev/null)"
done
echo "  --- first face line ---"
grep -m2 '^f ' $OBJ | sed 's/^/    /'
echo "  --- total lines: $(wc -l < $OBJ) ---"

echo
echo "=== frozen dark_wood texture set ==="
ls -la "$WS/models/pbr_textures/wood_textures/dark_wood.blend/textures/" 2>/dev/null | sed 's/^/  /'
echo "  --- the .blend itself ---"
ls -la "$WS/models/pbr_textures/wood_textures/" 2>/dev/null | sed 's/^/  /'

echo
echo "=== the exact pbr_material helper (what produced R/B=1.83) ==="
sed -n '78,155p' "$WS/code/scenarios/phyco_backdrops.py" | sed 's/^/  /'

echo
echo "=== asset.yaml visual block (where a material could be declared) ==="
sed -n '/^visual:/,/^visual_transform:/p' assets/objects/turntable/asset.yaml | sed 's/^/  /'
