#!/usr/bin/env bash
# Locate the BICYCLE(s) world AABB; full diagnostics, no grep filter.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BLEND="$REPO/assets/environments/replicad_apartment/visual/scene.blend"
R="$WS/models/backgrounds/replicad"

"$BLENDER" --background --factory-startup --python-expr "
import numpy as _np
if 'bool' not in _np.__dict__:
    _np.bool = _np.bool_
import bpy, json, os, traceback
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath='$BLEND')
env = bpy.data.objects['environment']
mw = env.matrix_world
print('BIKE env verts', len(env.data.vertices))

cfg = json.load(open('$R/configs/scenes/apt_0.scene_instance.json'))
insts = [i for i in cfg.get('object_instances', []) if 'bike' in i['template_name']]
print('BIKE instances', len(insts))
for inst in insts:
    tpl = inst['template_name'].split('/')[-1]
    glb = os.path.join('$R', 'objects', tpl + '.glb')
    print('BIKE try', glb, 'exists', os.path.isfile(glb))
    try:
        before = {o.name for o in bpy.data.objects}
        bpy.ops.import_scene.gltf(filepath=glb)
        new = [o for o in bpy.data.objects if o.name not in before]
        print('BIKE imported objects', len(new), [o.type for o in new])
        tr = inst.get('translation', [0,0,0])
        for o in new:
            if o.parent is None:
                o.location = (o.location.x + float(tr[0]),
                              o.location.y - float(tr[2]),
                              o.location.z + float(tr[1]))
        bpy.context.view_layer.update()
        meshes = [o for o in new if o.type == 'MESH']
        pts = []
        for o in meshes:
            m = o.matrix_world
            for c in o.bound_box:
                pts.append(m @ Vector(c))
        print('BIKE pts', len(pts))
        if pts:
            mn = [min(p[i] for p in pts) for i in range(3)]
            mx = [max(p[i] for p in pts) for i in range(3)]
            print('BIKE AABB %s min=(%.4f,%.4f,%.4f) max=(%.4f,%.4f,%.4f) dim=(%.4f,%.4f,%.4f) ctr=(%.4f,%.4f,%.4f)' % (
                tpl, mn[0],mn[1],mn[2], mx[0],mx[1],mx[2],
                mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2],
                (mn[0]+mx[0])/2,(mn[1]+mx[1])/2,(mn[2]+mx[2])/2))
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
    except Exception:
        traceback.print_exc()
print('BIKE DONE')
" 2>&1 | tail -40
echo "RC BIKE LOCATE2 DONE"
