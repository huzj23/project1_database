#!/usr/bin/env bash
# ===========================================================================
# T3 STEP 1: fix the stale floor metadata, and MEASURE the table top so a
# `table_top` region can be added for motions #5 (圆周) and #6 (转盘自转).
#
# The frozen turntable work (V3.2) recorded the table as:
#     table  frl_apartment_table_01
#     top z  0.7584 m   centre (0.414, 0.175)   span 1.399 x 0.852 x 0.742
#     disc centre z = 0.771
# but that must be re-verified against the CURRENT scene.blend, because the
# collision extraction work may have moved nothing but must not be assumed.
#
# Method: raycast straight down onto the table's bounding region and report the
# top surface, plus the clear rectangle on it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== 1) fix stale floor metadata (triangles + comment) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import re
p = "configs/maps.yaml"
s = open(p).read()
# actual face count of the re-extracted flat floor
s = re.sub(r"(\n                triangles: )202\b", r"\g<1>94", s)
old = """              # The scene's own floor slab replaces the old 2.89 m^2 box proxy.
              # Extracted by geometry from visual/scene.blend: upward faces with
              # z in [0.00, 0.05) -> 202 triangles, 81.61 m^2, footprint
              # x[-2.47, 4.00] y[-6.86, 4.76].  The simulator builds its
              # support body from this mesh instead of from bounds_xy."""
new = """              # The scene's own floor slab replaces the old 2.89 m^2 box proxy.
              # Extracted from visual/scene.blend keeping only faces whose ALL
              # THREE vertices lie within 1 cm of the floor plane and whose normal
              # is upward -> 94 triangles, 84.68 m^2, z in [-0.0416, 0.0007].
              #
              # The first attempt filtered on the FACE CENTRE z < 0.05 and kept
              # 202 faces / 81.61 m^2, but that admitted triangles spanning a
              # height change: raycasting then hit z = 0.084 at the placement
              # point, the actor rested 7.1 cm too high, and supported_fraction
              # collapsed to 0.012.  The all-vertices criterion removes them.
              #
              # The simulator builds its support body from this mesh instead of
              # from bounds_xy."""
assert old in s, "stale comment block not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("  triangles -> 94, comment corrected")
PY

echo
echo "=== 2) measure the table top in the CURRENT scene.blend ==="
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$REPO/assets/environments/replicad_apartment/visual/scene.blend" \
  --python-expr "
import bpy
from mathutils import Vector
dg = bpy.context.evaluated_depsgraph_get()
sc = bpy.context.scene
env = bpy.data.objects['environment']
# ReplicaCAD tables sit around x 0.4, y 0.2 per the frozen V3.2 record.
print('TB probing the table area')
zs = []
for x in [i*0.1 for i in range(-4, 9)]:
    for y in [i*0.1 for i in range(-8, 6)]:
        hit, loc, nrm, idx, obj, mat = sc.ray_cast(dg, Vector((x, y, 3.0)), Vector((0,0,-1)))
        if hit and 0.70 < loc.z < 0.82:
            zs.append((round(x,2), round(y,2), round(loc.z,4), round(nrm.z,2)))
print('TB candidates in z(0.70,0.82): %d' % len(zs))
xs = sorted(set(z[0] for z in zs)); ys = sorted(set(z[1] for z in zs))
if zs:
    print('TB x range: %.2f .. %.2f' % (min(xs), max(xs)))
    print('TB y range: %.2f .. %.2f' % (min(ys), max(ys)))
    import collections
    zc = collections.Counter(z[2] for z in zs)
    print('TB most common z:', zc.most_common(4))
    print('TB sample:', zs[:8])
" 2>&1 | grep -E '^TB'
