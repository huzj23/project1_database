"""Read the original source and named actors, without rendering or saving it."""
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path('/data/raw/huzijian/project1_database')
source = ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
deps = bpy.context.evaluated_depsgraph_get()
data = {'runtime': bpy.app.version_string, 'file_version': list(bpy.data.version),
        'source': str(source), 'scenes': [], 'native': []}
for scene in bpy.data.scenes:
    data['scenes'].append({'name': scene.name, 'engine': scene.render.engine,
                          'camera': scene.camera.name if scene.camera else None,
                          'resolution': [scene.render.resolution_x, scene.render.resolution_y,
                                         scene.render.resolution_percentage]})
for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    ev = obj.evaluated_get(deps)
    corners = [ev.matrix_world @ Vector(p) for p in ev.bound_box]
    low = [min(p[a] for p in corners) for a in range(3)]
    high = [max(p[a] for p in corners) for a in range(3)]
    near_radio = low[0] < -2.1 and high[0] > -3.1 and low[1] < 11.9 and high[1] > 10.8 and high[2] > .7
    if 'boombox' in obj.name or near_radio or obj.name in ['can_rusted.004', 'multi_cleaner_bottle.002']:
        mesh = ev.to_mesh()
        mesh.calc_loop_triangles()
        data['native'].append({'name': obj.name, 'bounds_min': low, 'bounds_max': high,
                               'vertices': len(mesh.vertices), 'triangles': len(mesh.loop_triangles),
                               'matrix_world': [list(row) for row in ev.matrix_world],
                               'modifiers': [m.type for m in obj.modifiers],
                               'materials': [m.name if m else None for m in mesh.materials]})
        ev.to_mesh_clear()
rest = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
out = Path(rest[0]) if rest else ROOT / 'log/V6.2_execution/source_341_probe.json'
if ROOT not in out.resolve().parents:
    raise ValueError('output outside project')
with out.open('x', encoding='utf-8') as handle:
    json.dump(data, handle, indent=2)
print(json.dumps(data, indent=2))
