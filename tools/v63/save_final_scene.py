"""Save-as (not raw-copy) the Blender archive, so relative paths are remapped."""
from pathlib import Path
import hashlib
import json
import bpy
import numpy as np

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'outcomes/v63/radio_scurve_domino/20261006_static_review'
target = OUT / 'review_scene.blend'
if target.exists():
    raise RuntimeError('refuse archived scene overwrite')
bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'tmp/v63_node11/static_scene_r5/review_scene.blend'))
for scene in bpy.data.scenes:
    scene.camera = bpy.data.objects['v63_05_full_route_overview']
    if scene.render.engine == 'CYCLES':
        scene.cycles.device = 'CPU'
    if scene.use_nodes:
        for node in scene.node_tree.nodes:
            if node.type == 'OUTPUT_FILE':
                node.base_path = str(OUT / ('compositor_' + scene.name))
bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=True)
bpy.ops.wm.open_mainfile(filepath=str(target))
checks = []
for obj in bpy.data.objects:
    if 'actor_id' not in obj:
        continue
    obj.data.calc_loop_triangles()
    v = np.array([list(v.co) for v in obj.data.vertices], dtype='<f8')
    t = np.array([list(t.vertices) for t in obj.data.loop_triangles], dtype='<i4')
    digest = hashlib.sha256(v.tobytes() + t.tobytes()).hexdigest()
    if digest != obj['common_shape_sha256'] or max(abs(s - 1) for s in obj.scale) > 1e-6:
        raise RuntimeError('saved scene common mesh identity failed')
    checks.append(obj.name)
missing = []
for img in bpy.data.images:
    if img.source == 'FILE' and not img.packed_file and img.filepath:
        path = Path(bpy.path.abspath(img.filepath)).resolve()
        if ROOT not in path.parents:
            raise RuntimeError('unpacked image points outside workspace')
        if not path.is_file():
            missing.append(str(path))
if missing:
    raise RuntimeError('missing unpacked images: ' + str(missing))
with (OUT / 'saved_scene_check.json').open('x') as handle:
    json.dump({'status': 'SAVE_REOPEN_COMMON_MESH_AND_IMAGE_PATH_PASS', 'mesh_parts': len(checks),
               'missing_unpacked_images': missing, 'active_camera': 'v63_05_full_route_overview',
               'full_physics_acceptance': False}, handle, indent=2)
print('ARCHIVED_SCENE_REOPEN_PASS', len(checks), flush=True)
