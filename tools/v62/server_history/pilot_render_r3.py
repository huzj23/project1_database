"""Server-only G1 pilot: three actors at table, original materials, aligned Fog.

This is an exploratory static image, NOT a passed physics or full-G1 delivery.
The original scene is read-only. Objects use their own source textures.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v62_node12/run_20261005_pilot3'
MODELS = ROOT / 'tmp/v62_shared_inputs/models'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
main = bpy.data.scenes['Scene']
bpy.context.window.scene = main
deps = bpy.context.evaluated_depsgraph_get()
original = {o.name: [list(row) for row in o.matrix_world] for o in bpy.data.objects}
original_lights = sorted(o.name for o in bpy.data.objects if o.type == 'LIGHT')
col = bpy.data.collections.new('v62_pilot_actors')
for scene in bpy.data.scenes:
    scene.collection.children.link(col)


def obj_geometry(path):
    verts, uvs, faces, uv_faces = [], [], [], []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            bits = line.split()
            if not bits:
                continue
            if bits[0] == 'v':
                verts.append([float(v) for v in bits[1:4]])
            elif bits[0] == 'vt':
                uvs.append([float(v) for v in bits[1:3]])
            elif bits[0] == 'f':
                face, tex = [], []
                for item in bits[1:]:
                    terms = item.split('/')
                    index = int(terms[0])
                    face.append(index - 1 if index > 0 else len(verts) + index)
                    tex.append(int(terms[1]) - 1 if len(terms) > 1 and terms[1] else -1)
                faces.append(face)
                uv_faces.append(tex)
    return np.asarray(verts), uvs, faces, uv_faces


def support_tree(name):
    ob = bpy.data.objects[name].evaluated_get(deps)
    mesh = ob.to_mesh()
    tree = BVHTree.FromPolygons([ob.matrix_world @ v.co for v in mesh.vertices],
                               [list(f.vertices) for f in mesh.polygons])
    ob.to_mesh_clear()
    return tree


table = support_tree('outdoor_table_chair_set_01_table.001')
floor = support_tree('Floor_main')
records = []


def add_asset(name, asset, xy, rotation, support='floor', z=None, role='candidate'):
    directory = MODELS / 'gso' / asset
    meshfile = directory / 'visual_geometry.obj'
    verts, texcoords, faces, uvfaces = obj_geometry(meshfile)
    centre = (verts.min(axis=0) + verts.max(axis=0)) / 2
    verts -= centre
    mesh = bpy.data.meshes.new('v62_' + name)
    mesh.from_pydata(verts.tolist(), [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name='UVMap')
    for polygon, indices in zip(mesh.polygons, uvfaces):
        for li, ti in zip(polygon.loop_indices, indices):
            if ti >= 0:
                layer.data[li].uv = texcoords[ti]
    ob = bpy.data.objects.new('v62_' + name, mesh)
    col.objects.link(ob)
    mat = bpy.data.materials.new('v62_own_' + asset)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = .55
    texture = mat.node_tree.nodes.new('ShaderNodeTexImage')
    texture.image = bpy.data.images.load(str(directory / 'texture.png'), check_existing=True)
    mat.node_tree.links.new(texture.outputs['Color'], bsdf.inputs['Base Color'])
    mesh.materials.append(mat)
    rotated = np.asarray([(rotation @ Vector(v)).to_tuple() for v in verts])
    minimum = rotated.min(axis=0)
    support_z = None
    if z is None:
        tree = table if support == 'table' else floor
        hit, _, _, _ = tree.ray_cast(Vector((xy[0], xy[1], 3)), Vector((0, 0, -1)), 5)
        if hit is None:
            raise RuntimeError('support query missed: ' + name)
        support_z = hit.z
        if support == 'table' and abs(support_z - .6857) > .003:
            raise RuntimeError('tabletop support missed or hit lower structure: ' + name)
        z = support_z - minimum[2] + .0003
    ob.matrix_world = Matrix.Translation(Vector((xy[0], xy[1], z))) @ rotation.to_4x4()
    records.append({'id': name, 'asset': asset, 'role': role, 'geometry': 'unmodified source visual mesh',
                    'own_texture': str(directory / 'texture.png'), 'source_center': centre.tolist(),
                    'source_dims': (verts.max(axis=0) - verts.min(axis=0)).tolist(),
                    'matrix_world': [list(row) for row in ob.matrix_world],
                    'support': support, 'support_z_at_centre': support_z,
                    'physics_status': 'NOT_VALIDATED; candidate visualization only'})
    return ob


# Source Paper Mario XY contains the cover, Z is thickness. This proper rigid
# rotation maps source Z->world X, source X->world Y, source Y->world Z.
upright = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))
receiver = add_asset('R', 'Paper_Mario_Sticker_Star_Nintendo_3DS_Game',
                     (-2.38, 11.27), upright, support='table', role='sole table-edge transfer object')

# Reuse the existing pool-table sphere mesh, recentered without scaling.
v, uv, f, uvf = obj_geometry(MODELS / 'phyco_sim_objs/pool_table/white_ball.obj')
centre = (v.min(axis=0) + v.max(axis=0)) / 2
v -= centre
mesh = bpy.data.meshes.new('v62_existing_cue_ball')
mesh.from_pydata(v.tolist(), [], f)
mesh.update()
for face in mesh.polygons:
    face.use_smooth = True
ball = bpy.data.objects.new('v62_B', mesh)
col.objects.link(ball)
ball.location = (-3.025, 10.83, 1.04)
mat = bpy.data.materials.new('v62_cue_ball_material')
mat.use_nodes = True
mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.82, .78, .67, 1)
mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .28
mesh.materials.append(mat)
records.append({'id': 'B', 'asset': 'pool_table/white_ball.obj', 'role': 'projectile initial state',
                'source_recenter': centre.tolist(), 'dims': (v.max(axis=0) - v.min(axis=0)).tolist(),
                'position': list(ball.location), 'provisional_velocity_m_s': [2.2, 2.8, -.5],
                'material': 'reconstructed ivory cue ball; not a scanned texture',
                'physics_status': 'NOT_VALIDATED'})

# Small landing receiver, then a short diverse pilot grouping on the existing
# hard floor. These are candidates, not a claimed solved or connected long chain.
add_asset('F01', 'Paper_Mario_Sticker_Star_Nintendo_3DS_Game', (-2.13, 11.27), upright)
add_asset('F02', 'Paper_Mario_Sticker_Star_Nintendo_3DS_Game', (-1.98, 11.29), upright)
add_asset('F03', 'Hasbro_Cranium_Performance_and_Acting_Game', (-1.75, 11.33), upright)
add_asset('F04', 'Hasbro_Trivial_Pursuit_Family_Edition_Game', (-1.46, 11.39), upright)
add_asset('F05', 'Paper_Mario_Sticker_Star_Nintendo_3DS_Game', (-1.22, 11.43), upright)
add_asset('Q', 'Shurtape_30_Day_Removal_UV_Delct_15', (-1.02, 11.46), upright,
          role='ring rolling relay candidate; hole preserved')
add_asset('F06', 'Paper_Mario_Sticker_Star_Nintendo_3DS_Game', (-.83, 11.50), upright)
add_asset('L', 'LEGO_Bricks_More_Creative_Suitcase', (-.46, 11.59), upright,
          role='thick package candidate; original handle/opening retained')

camera_specs = [
    ('01_table_story', (-1.25, 9.95, 1.42), (-2.57, 11.22, .88), 42),
    ('03_drop_bridge', (-.95, 10.20, .95), (-2.23, 11.27, .48), 45),
    ('05_tape_and_suitcase', (-.15, 10.05, .52), (-1.03, 11.44, .12), 48),
]

# Correct the renderer's cross-scene alignment, without removing author effects.
def bind_camera(camera):
    bindings = []
    for scene in bpy.data.scenes:
        if camera.name not in scene.objects:
            scene.collection.objects.link(camera)
        scene.camera = camera
        scene.frame_set(1)
        scene.render.resolution_x = 1280
        scene.render.resolution_y = 720
        scene.render.resolution_percentage = 100
        scene.render.pixel_aspect_x = 1
        scene.render.pixel_aspect_y = 1
        scene.render.use_border = False
        scene.render.use_crop_to_border = False
        if scene.render.engine == 'CYCLES':
            scene.cycles.samples = 24
            scene.cycles.use_denoising = True
            scene.cycles.device = 'GPU'
        elif hasattr(scene, 'eevee'):
            scene.eevee.taa_render_samples = 8
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 12
        if scene.use_nodes:
            for node in scene.node_tree.nodes:
                if node.type == 'OUTPUT_FILE':
                    node.base_path = str(OUT / ('compositor_' + scene.name))
        bindings.append({'scene': scene.name, 'camera': scene.camera.name,
                         'matrix': [list(row) for row in scene.camera.matrix_world],
                         'resolution': [scene.render.resolution_x, scene.render.resolution_y, 100],
                         'frame': scene.frame_current, 'engine': scene.render.engine,
                         'compositor': scene.render.use_compositing,
                         'layers': [{'name': lay.name, 'material_override':
                                     lay.material_override.name if lay.material_override else None}
                                    for lay in scene.view_layers]})
    return bindings


preferences = bpy.context.preferences.addons['cycles'].preferences
preferences.compute_device_type = 'CUDA'
preferences.get_devices()
devices = []
for device in preferences.devices:
    device.use = device.type == 'CUDA'
    devices.append({'id': device.id, 'name': device.name, 'type': device.type, 'use': device.use})
if not any(device['use'] for device in devices):
    raise RuntimeError('No authorized CUDA device enumerated; no silent CPU/local fallback')

report = {'status': 'PILOT_ONLY_NOT_G1_ACCEPTANCE', 'objects': records, 'devices': devices,
          'radio': {'name': 'boombox.002', 'initial_pose_changed': False,
                    'dynamic_feasibility': 'NOT_VALIDATED'},
          'missing_full_chain': True, 'render_results': []}
for ident, pos, aim, lens in camera_specs:
    cam_data = bpy.data.cameras.new('v62_' + ident)
    cam_data.lens = lens
    cam_data.sensor_width = 36
    cam_data.clip_start = .05
    cam_data.clip_end = 1500
    cam = bpy.data.objects.new('v62_' + ident, cam_data)
    cam.location = pos
    cam.rotation_euler = (Vector(aim) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    bindings = bind_camera(cam)
    bpy.context.window.scene = main
    image_path = OUT / (ident + '.png')
    if image_path.exists():
        raise RuntimeError('refuse image overwrite')
    main.render.filepath = str(image_path)
    main.render.image_settings.file_format = 'PNG'
    main.render.image_settings.color_mode = 'RGB'
    start = time.time()
    bpy.ops.render.render(write_still=True, scene=main.name)
    report['render_results'].append({'id': ident, 'file': str(image_path),
                                      'seconds': time.time() - start, 'bindings': bindings})
    (OUT / 'pilot_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PILOT_FINISHED', ident, flush=True)

changed = [name for name, matrix in original.items()
           if [list(row) for row in bpy.data.objects[name].matrix_world] != matrix]
report['author_objects_transform_changes'] = changed
report['author_lights_unchanged'] = sorted(o.name for o in bpy.data.objects if o.type == 'LIGHT') == original_lights
if changed or not report['author_lights_unchanged']:
    raise RuntimeError('unexpected author scene change')
report['note'] = 'Visual pilot only. No physics success, common-shape identity, full-chain or contact gate has passed.'
(OUT / 'pilot_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'pilot.blend'))
