#!/usr/bin/env bash
# ===========================================================================
# AUDIT our own assets against the mentor's published asset conventions
# (physics-video-sim assets/README.md, commit 7a68a71).
#
# The mentor's rule, quoted by the user:
#   "加入新资产需要进行处理和相应配置，物体和场景需要归一化然后设置碰撞体，
#    处理好assets，把所有东西都设为被动项，后面直接用就行了"
# i.e. normalize, give it a collision body, follow the assets/ layout, make the
# scene furniture passive/static, and it is then reusable as-is.
#
# Required per assets/README.md:
#   objects/<id>/      asset.yaml + license/SOURCE.md + source/ + visual/model.glb
#                      + collision/<low-poly mesh + urdf>
#   environments/<id>/ asset.yaml + license/SOURCE.md + source/ + visual/scene.blend
#                      + collision/surfaces/<mesh + urdf>
#   naming: <category>_<minimal_name>, lowercase ASCII; category in
#           sphere|cylinder|cube|cone|food|special
#   collision: primitive only for sphere/cylinder/cube/cone; others need a low-poly
#              mesh (<=512 tris default), NOT a bounding sphere and NOT the high-poly visual
#   manifest must record: sha256, size, scale, bounding_radius, support_height,
#              initial_orientation.quaternion_wxyz, collision + physics ranges
#   environments: baked, merged to ONE mesh named `environment`, textures packed,
#              authored lights kept in collection `environment_lighting`,
#              authored World kept as `environment_world`
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== OUR assets present ==="
ls assets/objects/ | sed 's/^/  obj: /'
ls assets/environments/ | sed 's/^/  env: /'

echo
echo "=== structure of the two assets we need to ship ==="
for a in assets/objects/gso_sootheze_cold_therapy_elephant \
         assets/environments/replicad_apartment; do
  echo "  --- $a ---"
  find "$a" -type f -printf '    %8s  %p\n' 2>/dev/null | sort -k2
done

echo
echo "=== asset.yaml: elephant ==="
cat assets/objects/gso_sootheze_cold_therapy_elephant/asset.yaml | sed 's/^/  /'

echo
echo "=== asset.yaml: replicad_apartment ==="
cat assets/environments/replicad_apartment/asset.yaml | sed 's/^/  /'

echo
echo "=== mentor's OWN reference object manifest (food_lime) ==="
cat assets/objects/food_lime/asset.yaml | sed 's/^/  /'
echo "  --- its files ---"
find assets/objects/food_lime -type f -printf '    %8s  %p\n' 2>/dev/null | sort -k2

echo
echo "=== mentor's OWN reference environment manifest (classroom) ==="
cat assets/environments/classroom/asset.yaml | sed 's/^/  /'
