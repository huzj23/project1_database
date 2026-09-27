#!/usr/bin/env bash
# ===========================================================================
# STEP 1: extract the scene's OWN floor slab as a static collision mesh/URDF,
# replacing the "垃圾补丁地板" (the 2.89 m^2 box patch).
#
# Why mesh collision and not a bigger box:
#   * a box spanning the whole apartment would also cover the stairs and would
#     intersect furniture, so it is not a drop-in replacement
#   * the mentor's own pattern for irregular surfaces is `collision: type: mesh`
#     with an extracted static URDF (see classroom_student_desk_a in maps.yaml)
#   * the floor slab is only 36 triangles, far below the 2048 max_faces default
#
# What we must locate inside scene.blend:
#   the floor slab (Mesh.561 in the source GLB, 91 verts, extents 7.256 x 0.043
#   x 12.993 m, at z ~ 0.0007).  After joining, it is part of the single
#   "environment" object, so we select it BY GEOMETRY: all faces whose vertices
#   lie within a thin band around the floor height.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ENVDIR="$REPO/assets/environments/replicad_apartment"

echo "=== the extraction tool's full CLI ==="
sed -n '1,68p' "$REPO/scripts/generate_environment_surface_collision.py" | sed 's/^/  /'
