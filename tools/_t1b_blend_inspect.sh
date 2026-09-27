#!/usr/bin/env bash
# Inspect the replicad apartment scene.blend: object inventory + world bounds.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BLEND="$REPO/assets/environments/replicad_apartment/visual/scene.blend"
echo "BLEND=$BLEND"
ls -la "$BLEND"
"$BLENDER" --background --factory-startup --python-expr "
import bpy
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath='$BLEND')
print('OBJCOUNT', len(bpy.data.objects))
for o in sorted(bpy.data.objects, key=lambda x: x.name):
    if o.type != 'MESH':
        print('OBJ', o.type, o.name)
        continue
    mw = o.matrix_world
    pts = [mw @ Vector(c) for c in o.bound_box]
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    print('OBJ MESH %-42s min=(%.3f,%.3f,%.3f) max=(%.3f,%.3f,%.3f) dim=(%.3f,%.3f,%.3f) tris=%d parent=%s' % (
        o.name, mn[0],mn[1],mn[2], mx[0],mx[1],mx[2],
        mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2],
        len(o.data.polygons), o.parent.name if o.parent else '-'))
print('COLLECTIONS', [c.name for c in bpy.data.collections])
print('WORLDS', [w.name for w in bpy.data.worlds])
" 2>&1 | grep -E '^OBJ|^OBJCOUNT|^COLLECTIONS|^WORLDS|^BLEND'
echo "RC BLEND INSPECT DONE"
