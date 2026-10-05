"""Build a read-only-source G1 review scene using the common physical meshes.

Static composition only: no animation, impulses or full-chain success claim.
Run with project Blender in tmux, never with a desktop/local renderer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path('/data/raw/huzijian/project1_database')
ap = argparse.ArgumentParser()
ap.add_argument('--layout', required=True)
ap.add_argument('--out', required=True)
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])


def checked(value):
    value = Path(value).resolve()
    if ROOT not in value.parents:
        raise ValueError('outside workspace')
    return value


OUT = checked(args.out)
OUT.mkdir(parents=True, exist_ok=False)
layout_path = checked(args.layout)
layout = json.loads(layout_path.read_text())
if layout['status'] != 'INITIAL_LAYOUT_PASS_PENDING_RELAY':
    raise RuntimeError('failed initial/stability layout; refusing acceptance render')
common = checked(layout['common_manifest'])
assets = json.loads(common.read_text())['assets']
SOURCE = ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


source_hash = digest(SOURCE)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
main = bpy.data.scenes['Scene']
bpy.context.window.scene = main
original_transforms = {o.name: [list(row) for row in o.matrix_world] for o in bpy.data.objects}
original_lights = {o.name: {'type': o.data.type, 'energy': o.data.energy,
                           'color': list(o.data.color)}
                   for o in bpy.data.objects if o.type == 'LIGHT'}
original_scenes = {s.name: {'world': s.world.name if s.world else None,
                           'engine': s.render.engine,
                           'view_transform': s.view_settings.view_transform,
                           'exposure': s.view_settings.exposure,
                           'gamma': s.view_settings.gamma,
                           'compositor_nodes': [(n.name, n.bl_idname) for n in s.node_tree.nodes]
                            if s.use_nodes else []} for s in bpy.data.scenes}
col = bpy.data.collections.new('v63_common_actors')
for scene in bpy.data.scenes:
    scene.collection.children.link(col)

template_rows = []
for key, asset in assets.items():
    template_rows.extend(asset.get('parts', [asset]))
wanted = tuple(row['object'] for row in template_rows)
with bpy.data.libraries.load(str(common.parent / 'common_assets.blend'), link=False) as (src, dst):
    if not set(wanted).issubset(src.objects):
        raise RuntimeError('common library incomplete')
    dst.objects = list(wanted)
templates = dict(zip(wanted, dst.objects))
identity_checks = []
for row in template_rows:
    obj = templates[row['object']]
    obj.data.calc_loop_triangles()
    vertices = np.array([list(v.co) for v in obj.data.vertices], dtype='<f8')
    triangles = np.array([list(t.vertices) for t in obj.data.loop_triangles], dtype='<i4')
    shape_hash = hashlib.sha256(vertices.tobytes() + triangles.tobytes()).hexdigest()
    if shape_hash != row['shape_sha256'] or obj.modifiers:
        raise RuntimeError('common shape changed: ' + obj.name)
    identity_checks.append({'object': obj.name, 'sha256': shape_hash, 'status': 'EXACT_LIBRARY_NPZ_MATCH'})

actors = {}
actor_records = []


def add_actor(ident, key, position, quat=(0., 0., 0., 1.)):
    asset = assets[key]
    body_matrix = Matrix.Translation(Vector(position)) @ Quaternion((quat[3], *quat[:3])).to_matrix().to_4x4()
    actor_parts = []
    for index, row in enumerate(asset.get('parts', [asset])):
        obj = templates[row['object']].copy()
        obj.name = 'v63_%s_%02d' % (ident, index)
        col.objects.link(obj)
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.matrix_world = body_matrix
        obj['actor_id'] = ident
        obj['common_shape_sha256'] = row['shape_sha256']
        obj['asset_key'] = key
        actor_parts.append(obj)
    actors[ident] = actor_parts
    actor_records.append({'id': ident, 'asset_key': key, 'asset_id': asset['asset_id'],
                          'position': list(position), 'quaternion_xyzw': list(quat),
                          'scale': [1, 1, 1], 'mesh_objects': [o.name for o in actor_parts],
                          'mass_kg_estimate_not_measurement': asset['mass_estimate_kg']})


original_radio = bpy.data.objects['boombox.002']
original_radio.hide_render = True
original_radio.hide_set(True)
add_actor('A', 'radio', assets['radio']['initial_centre'])
add_actor('B', 'baseball', [-3.025, 11.30, .95])
add_actor('R', 'paper', [-2.38, 11.27, .685922 + assets['paper']['dims'][2] / 2 + .0003])
for row in layout['objects']:
    # Use the tested settled state. Do not lift objects just for the picture.
    add_actor(row['id'], row['asset_key'], row['settled_position'], row['settled_quaternion_xyzw'])


def xyz(ident):
    return np.array(next(row['position'] for row in actor_records if row['id'] == ident))


camera_specs = [
    ('01_ball_and_table', (-1.70, 9.95, 1.67), (-2.65, 11.27, .85), 40, ['A', 'B', 'R']),
    ('02_ball_material_check', (-3.30, 10.91, 1.16), (-3.025, 11.30, .95), 52, ['B']),
    ('03_radio_receiver_side', (-2.88, 10.12, 1.42), (-2.66, 11.27, .86), 35, ['A', 'B', 'R']),
    ('04_drop_bridge', (-.70, 9.65, 1.60), (-2.20, 11.40, .50), 40, ['A', 'R', 'F01', 'F04']),
    ('05_full_route_overview', (1.62, 8.30, 4.20), (-.85, 11.95, .16), 38, list(actors)),
    ('06_first_curve', (-.50, 10.60, 1.28), (-1.31, 12.26, .12), 36, ['F07', 'F12', 'F18']),
    ('07_tape_bridge', tuple(xyz('F22') + [0., -1.12, .54]), tuple(xyz('F22') + [0., 0., .06]), 48,
     ['F20', 'F21', 'F22', 'F23', 'F24']),
    ('08_reverse_curve', (1.93, 10.10, 1.85), (.47, 11.82, .10), 35, ['F26', 'F32', 'F39', 'F43']),
    ('09_finish', (1.95, 11.60, 1.11), (.91, 12.67, .10), 38, ['F43', 'F44', 'F45', 'F48']),
    ('10_follow_camera_sample', tuple(xyz('F30') + [.60, -1.25, .62]), tuple(xyz('F30') + [.10, .05, .07]),
     36, ['F28', 'F29', 'F30', 'F31', 'F32']),
]
camera_records = []
for ident, position, aim, lens, targets in camera_specs:
    data = bpy.data.cameras.new('v63_' + ident)
    data.lens = lens
    data.sensor_width = 36
    data.clip_start = .025
    data.clip_end = 1500
    data.dof.use_dof = False
    cam = bpy.data.objects.new('v63_' + ident, data)
    cam.location = position
    cam.rotation_euler = (Vector(aim) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for scene in bpy.data.scenes:
        scene.collection.objects.link(cam)
    camera_records.append({'id': ident, 'camera_object': cam.name, 'position': list(position),
                           'aim': list(aim), 'lens_mm': lens, 'targets': targets})

for scene in bpy.data.scenes:
    scene.camera = bpy.data.objects[camera_records[0]['camera_object']]
    scene.frame_set(1)
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.use_border = scene.render.use_crop_to_border = False
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 16
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    if scene.render.engine == 'CYCLES':
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 24
        scene.cycles.use_denoising = True
        scene.render.use_persistent_data = True
    elif hasattr(scene, 'eevee'):
        scene.eevee.taa_render_samples = 8
    if scene.use_nodes:
        for node in scene.node_tree.nodes:
            if node.type == 'OUTPUT_FILE':
                node.base_path = str(OUT / ('compositor_' + scene.name))

bpy.context.view_layer.update()
for camrow in camera_records:
    cam = bpy.data.objects[camrow['camera_object']]
    bounds = {}
    for ident in camrow['targets']:
        coords = [world_to_camera_view(main, cam, obj.matrix_world @ Vector(corner))
                  for obj in actors[ident] for corner in obj.bound_box]
        bounds[ident] = {'xmin': min(c.x for c in coords), 'xmax': max(c.x for c in coords),
                         'ymin': min(c.y for c in coords), 'ymax': max(c.y for c in coords),
                         'minimum_depth': min(c.z for c in coords)}
    camrow['projected_target_bounds'] = bounds
    camrow['occlusion_status'] = 'VISUAL_REVIEW_REQUIRED; projected bounds are not a ray-clearance proof'

changed = [name for name, matrix in original_transforms.items()
           if [list(row) for row in bpy.data.objects[name].matrix_world] != matrix]
current_lights = {o.name: {'type': o.data.type, 'energy': o.data.energy, 'color': list(o.data.color)}
                  for o in bpy.data.objects if o.type == 'LIGHT'}
if changed or current_lights != original_lights or digest(SOURCE) != source_hash:
    raise RuntimeError('unexpected authored scene mutation')
report = {'status': 'G1_STATIC_REVIEW_NOT_FULL_PHYSICS_PASS', 'source': str(SOURCE),
          'source_sha256': source_hash, 'layout_source': str(layout_path), 'layout_sha256': digest(layout_path),
          'common_manifest': str(common), 'common_sha256': digest(common),
          'ground_count': layout['ground_count'], 'all_actor_count': len(actors),
          'ground_asset_types': layout['ground_asset_types'], 'route_length_m': layout['route_length_m'],
          'arc_radii_m': layout['arc_radii_m'], 'actors': actor_records, 'cameras': camera_records,
          'shape_identity': identity_checks, 'original_lights': original_lights,
          'original_scenes': original_scenes, 'author_transform_changes': changed,
          'declared_author_change': 'Original boombox.002 hidden; 37 source-material common rigid parts at its original pose.',
          'added_scene_content': '50 new actors plus common radio replacement, review cameras; NO added lamp/floor/rail.',
          'stability': layout['settle'],
          'physics_remaining': ['representative relay checks', 'table-ground bridge', 'complete chain',
                                'independent penetration checks', 'timestep/parameter robustness', 'moving camera clearance'],
          'ball_initial_velocity_m_s': [7., 0., -1.8119098615],
          'ball_mechanism_status': '960/1920 Hz same qualitative outcome; cached penetration gate not passed'}
with (OUT / 'composition_report.json').open('x') as handle:
    json.dump(report, handle, indent=2)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'review_scene.blend'), check_existing=True)
print('COMPOSED_STATIC', str(OUT), len(actors), flush=True)
