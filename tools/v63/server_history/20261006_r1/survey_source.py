"""CPU-only evaluated scene survey; no render, author changes, or GPU context."""
from pathlib import Path
import json
import time
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node11/survey_r1'
OUT.mkdir(parents=True, exist_ok=False)
SOURCE = ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
bpy.context.window.scene = bpy.data.scenes['Scene']
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
roi_min = np.array([-3.6, 9.5, -.065])
roi_max = np.array([4.6, 16., 1.6])
report = {'status': 'READ_ONLY_SURVEY', 'roi_min': roi_min.tolist(), 'roi_max': roi_max.tolist(),
          'objects': [], 'excluded': [], 'floor_samples': []}
all_verts, all_tri = [], []
vertex_offset = 0
start = time.time()
for instance in deps.object_instances:
    obj = instance.object
    if obj.type != 'MESH' or obj.hide_render:
        continue
    if hasattr(instance, 'show_self') and not instance.show_self:
        continue
    matrix = instance.matrix_world
    bounds = np.asarray([list(matrix @ Vector(c)) for c in obj.bound_box])
    if np.any(bounds.max(0) < roi_min) or np.any(bounds.min(0) > roi_max):
        continue
    if obj.name == 'boombox.002':
        report['excluded'].append({'name': obj.name, 'reason': 'intended dynamic actor, exported in V6.2'})
        continue
    mesh = obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        verts = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get('co', verts)
        verts = verts.reshape((-1, 3))
        mat = np.asarray(matrix, dtype=np.float64)
        verts = verts @ mat[:3, :3].T + mat[:3, 3]
        triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get('vertices', triangles)
        triangles = triangles.reshape((-1, 3))
        tv = verts[triangles]
        mask = np.all(tv.max(1) >= roi_min, axis=1) & np.all(tv.min(1) <= roi_max, axis=1)
        triangles = triangles[mask]
        if not len(triangles):
            continue
        indices, inverse = np.unique(triangles, return_inverse=True)
        verts = verts[indices]
        triangles = inverse.reshape((-1, 3)).astype(np.int32)
        index = len(report['objects'])
        filename = 'static_%04d.npz' % index
        np.savez_compressed(OUT / filename, vertices=verts, triangles=triangles)
        report['objects'].append({'name': obj.name, 'instance': instance.is_instance,
                                  'persistent_id': list(instance.persistent_id), 'file': filename,
                                  'min': verts.min(0).tolist(), 'max': verts.max(0).tolist(),
                                  'vertices': len(verts), 'triangles': len(triangles),
                                  'matrix': mat.tolist(),
                                  'visible_camera': getattr(obj, 'visible_camera', None)})
        # Ground occupancy should include the authored visible scatter, not just a flat Floor_main.
        if getattr(obj, 'visible_camera', True):
            all_verts.extend(verts.tolist())
            all_tri.extend((triangles + vertex_offset).tolist())
            vertex_offset += len(verts)
    finally:
        obj.to_mesh_clear()
print('EXPORTED_STATICS', len(report['objects']), 'triangles', len(all_tri), flush=True)
tree = BVHTree.FromPolygons(all_verts, all_tri, all_triangles=True)
for x in np.arange(-2.4, 4.301, .1):
    for y in np.arange(10.5, 15.501, .1):
        hit, normal, face, dist = tree.ray_cast(Vector((x, y, .5)), Vector((0, 0, -1)), .60)
        if hit is not None:
            report['floor_samples'].append([round(float(x), 3), round(float(y), 3),
                                            float(hit.z), float(normal.z)])
report['elapsed_s'] = time.time() - start
report['all_scene_objects'] = len(bpy.data.objects)
report['roi_static_count'] = len(report['objects'])
with (OUT / 'survey.json').open('x', encoding='utf8') as handle:
    json.dump(report, handle, indent=2)
print('SURVEY_COMPLETE', report['elapsed_s'], flush=True)
