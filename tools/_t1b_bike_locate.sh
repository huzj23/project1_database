#!/usr/bin/env bash
# ===========================================================================
# Locate the BICYCLE(s) inside the merged ReplicaCAD environment mesh.
#
# scene.blend merges stage + all 113 props into ONE mesh named "environment",
# so the bike cannot be found by object name.  This script re-imports the two
# bike GLBs with the exact placement transform used by export_scene_blend.sh and
# (a) reports their world AABB, (b) checks whether their vertices coincide with
# vertices of the merged environment mesh (which would let us extract the exact
# bike faces for a pixel-exact prominence measurement).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BLEND="$REPO/assets/environments/replicad_apartment/visual/scene.blend"
R="$WS/models/backgrounds/replicad"

"$BLENDER" --background --factory-startup --python-expr "
import bpy, json, math
from mathutils import Vector, kdtree

bpy.ops.wm.open_mainfile(filepath='$BLEND')
env = bpy.data.objects['environment']
mw = env.matrix_world
verts = env.data.vertices
print('BIKE env verts', len(verts), 'polys', len(env.data.polygons))
kd = kdtree.KDTree(len(verts))
for i, v in enumerate(verts):
    kd.insert(mw @ v.co, i)
kd.balance()

cfg = json.load(open('$R/configs/scenes/apt_0.scene_instance.json'))
insts = [i for i in cfg.get('object_instances', []) if 'bike' in i['template_name']]
print('BIKE instances', len(insts))
for inst in insts:
    tpl = inst['template_name'].split('/')[-1]
    glb = '$R/objects/' + tpl + '.glb'
    before = {o.name for o in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=glb)
    new = [o for o in bpy.data.objects if o.name not in before]
    tr = inst.get('translation', [0,0,0])
    for o in new:
        if o.parent is None:
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == 'MESH']
    pts = []
    wv = []
    for o in meshes:
        m = o.matrix_world
        for c in o.bound_box:
            pts.append(m @ Vector(c))
        for v in o.data.vertices:
            wv.append(m @ v.co)
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    print('BIKE %s meshes=%d verts=%d' % (tpl, len(meshes), len(wv)))
    print('BIKE %s AABB min=(%.4f,%.4f,%.4f) max=(%.4f,%.4f,%.4f) dim=(%.4f,%.4f,%.4f) ctr=(%.4f,%.4f,%.4f)' % (
        tpl, mn[0],mn[1],mn[2], mx[0],mx[1],mx[2],
        mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2],
        (mn[0]+mx[0])/2,(mn[1]+mx[1])/2,(mn[2]+mx[2])/2))
    hit = 0
    dmax = 0.0
    for p in wv:
        co, idx, dist = kd.find(p)
        if dist < 2e-4:
            hit += 1
            dmax = max(dmax, dist)
    print('BIKE %s vertex-match %d/%d (max matched dist %.6f)' % (tpl, hit, len(wv), dmax))
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
print('BIKE DONE')
" 2>&1 | grep -E '^BIKE'
echo "RC BIKE LOCATE DONE"
