"""Repair one legacy path to its existing identical authored resource, new copy.

Keep the pre-relink review_scene.blend and PNGs untouched for exact provenance.
Do not claim already-rendered PNGs were re-rendered after this path repair.
"""
from pathlib import Path
import hashlib
import json
import bpy
import numpy as np

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'outcomes/v63/radio_scurve_domino/20261006_static_review'
target = OUT / 'review_scene_relinked.blend'
if target.exists():
    raise RuntimeError('refuse overwrite')
bpy.ops.wm.open_mainfile(filepath=str(OUT / 'review_scene.blend'))
name = 'modular_urban_apartments_facade_trim_01_rough.png'
img = bpy.data.images[name]
old = bpy.path.abspath(img.filepath)
source = ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/textures' / name
if not source.is_file():
    raise RuntimeError('authored source not present')
img.filepath = str(source)
img.reload()
if min(img.size) < 1:
    raise RuntimeError('authored texture reload failed')
bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=True)
bpy.ops.wm.open_mainfile(filepath=str(target))
count = 0
for obj in bpy.data.objects:
    if 'actor_id' not in obj:
        continue
    obj.data.calc_loop_triangles()
    v = np.array([list(v.co) for v in obj.data.vertices], dtype='<f8')
    t = np.array([list(t.vertices) for t in obj.data.loop_triangles], dtype='<i4')
    if hashlib.sha256(v.tobytes() + t.tobytes()).hexdigest() != obj['common_shape_sha256']:
        raise RuntimeError('common mesh changed')
    count += 1
missing = []
for item in bpy.data.images:
    if item.source == 'FILE' and not item.packed_file and item.filepath:
        path = Path(bpy.path.abspath(item.filepath)).resolve()
        if ROOT not in path.parents or not path.is_file():
            missing.append(str(path))
if missing:
    raise RuntimeError('dependency audit still fails: ' + str(missing))
with (OUT / 'saved_scene_check.json').open('x') as handle:
    json.dump({'status': 'RELINKED_COPY_SAVE_REOPEN_MESH_AND_DEPENDENCY_PASS',
               'file': str(target), 'mesh_parts': count, 'missing_unpacked_images': missing,
               'relink': {'image': name, 'old_path': old, 'new_path': str(source),
                          'sha256': hashlib.sha256(source.read_bytes()).hexdigest()},
               'original_preview_scene_retained': str(OUT / 'review_scene.blend'),
               'preview_pngs_rerendered_after_relink': False,
               'required_before_G2': 'Re-render affected static views using relinked copy; do not treat old PNGs as repaired-path evidence.',
               'full_physics_acceptance': False}, handle, indent=2)
print('RELINKED_COPY_VERIFIED', count, flush=True)
