"""Read-only audit of a missing authored texture reference in archived scene."""
from pathlib import Path
import json
import bpy

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'outcomes/v63/radio_scurve_domino/20261006_static_review'
bpy.ops.wm.open_mainfile(filepath=str(OUT / 'review_scene.blend'))
rows = []
trees = [(m.name, 'MATERIAL', m.node_tree) for m in bpy.data.materials if m.use_nodes]
trees += [(g.name, 'GROUP', g) for g in bpy.data.node_groups]
trees += [(w.name, 'WORLD', w.node_tree) for w in bpy.data.worlds if w.use_nodes]
for img in bpy.data.images:
    if img.source != 'FILE' or img.packed_file or not img.filepath:
        continue
    path = Path(bpy.path.abspath(img.filepath)).resolve()
    if ROOT not in path.parents:
        raise RuntimeError('external unpacked image path refused')
    if path.is_file():
        continue
    refs = []
    for name, kind, tree in trees:
        for node in tree.nodes:
            if getattr(node, 'image', None) == img:
                objects = [o.name for o in bpy.data.objects if hasattr(o.data, 'materials')
                           and name in [m.name for m in o.data.materials if m]] if kind == 'MATERIAL' else []
                refs.append({'tree': name, 'kind': kind, 'node': node.name, 'linked':
                             any(socket.is_linked for socket in node.outputs), 'objects': objects})
    rows.append({'image': img.name, 'path': str(path), 'users': img.users,
                 'fake_user': img.use_fake_user, 'references': refs})
with (OUT / 'image_dependency_audit_r1.json').open('x') as handle:
    json.dump({'missing': rows}, handle, indent=2)
print(json.dumps({'missing': rows}, indent=2), flush=True)
