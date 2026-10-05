"""Read-only source geometry export and support survey, in server Blender."""
from pathlib import Path
import json
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'log/V6.2_execution/geometry_audit'
OUT.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'))
bpy.context.window.scene = bpy.data.scenes['Scene']
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
names = ['boombox.002', 'outdoor_table_chair_set_01_table.001', 'Floor_main',
         'outdoor_table_chair_set_01_chair_01.001', 'outdoor_table_chair_set_01_chair_02.001']
report = {'objects': {}, 'render_layers': {}, 'table_grid_hits': []}
for name in names:
    ob = bpy.data.objects[name].evaluated_get(deps)
    mesh = ob.to_mesh()
    mesh.calc_loop_triangles()
    vertices = np.asarray([list(ob.matrix_world @ v.co) for v in mesh.vertices])
    local = np.asarray([list(v.co) for v in mesh.vertices])
    triangles = np.asarray([list(f.vertices) for f in mesh.loop_triangles], dtype=np.int32)
    np.savez_compressed(OUT / (name + '.npz'), vertices=vertices, local_vertices=local,
                        triangles=triangles, matrix=np.asarray(ob.matrix_world))
    row = {'vertices': len(vertices), 'triangles': len(triangles),
           'min': vertices.min(axis=0).tolist(), 'max': vertices.max(axis=0).tolist()}
    if name == 'boombox.002':
        parent = list(range(len(vertices)))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b, c in triangles:
            parent[find(int(b))] = find(int(a))
            parent[find(int(c))] = find(int(a))
        groups = {}
        for i in range(len(vertices)):
            groups.setdefault(find(i), []).append(i)
        comps = []
        for indices in sorted(groups.values(), key=len, reverse=True):
            vv, lv = vertices[indices], local[indices]
            comps.append({'indices': indices, 'count': len(indices),
                          'min': vv.min(axis=0).tolist(), 'max': vv.max(axis=0).tolist(),
                          'local_min': lv.min(axis=0).tolist(), 'local_max': lv.max(axis=0).tolist()})
        row['components'] = comps
    if name == 'outdoor_table_chair_set_01_table.001':
        tree = BVHTree.FromPolygons([Vector(v) for v in vertices], triangles.tolist(), all_triangles=True)
        for x in np.arange(-2.40, -2.19, .01):
            for y in np.arange(11.20, 11.401, .01):
                hit, normal, face, distance = tree.ray_cast(Vector((x, y, 1.3)), Vector((0, 0, -1)), 1.5)
                if hit is not None and abs(hit.z - .6857) < .003:
                    report['table_grid_hits'].append([round(x, 3), round(y, 3), round(hit.z, 6)])
    report['objects'][name] = row
    ob.to_mesh_clear()
for scene in bpy.data.scenes:
    report['render_layers'][scene.name] = {
        'compositor': [{'name': n.name, 'type': n.type, 'scene': n.scene.name if n.scene else None, 'layer': n.layer}
                       for n in scene.node_tree.nodes if n.type == 'R_LAYERS'] if scene.use_nodes else [],
        'layers': [{'name': v.name, 'override': v.material_override.name if v.material_override else None}
                   for v in scene.view_layers],
        'lights': [o.name for o in scene.objects if o.type == 'LIGHT']}
(OUT / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('GEOMETRY_AUDIT_COMPLETE', str(OUT), flush=True)
