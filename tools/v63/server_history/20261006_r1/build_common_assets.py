"""CPU asset preparation: common solids, own texture transfer, immutable library.

Only derived data is changed. The author's background and source models stay
unchanged. Raw scans are retained as hidden bake references, never rendered.
"""
from pathlib import Path
import hashlib
import json
import math
import time
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node11/common_assets_r1'
INPUT = ROOT / 'tmp/v63_shared_inputs/models/gso'
PROBE = ROOT / 'tmp/v63_node11/baseball_probe_r3'
OUT.mkdir(parents=True, exist_ok=False)
(OUT / 'textures').mkdir()
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 4
scene.render.threads_mode = 'FIXED'
scene.render.threads = 8
for obj in bpy.data.objects:
    obj.hide_render = True
    obj.hide_set(True)
assets = {}
outputs = []

SPECS = {
    'paper': ('Paper_Mario_Sticker_Star_Nintendo_3DS_Game', [[0, 0, 1], [1, 0, 0], [0, 1, 0]], .07),
    'wii': ('New_Super_Mario_BrosWii_Wii_Game', [[0, 0, 1], [1, 0, 0], [0, 1, 0]], .12),
    'dvd': ('House_of_Cards_The_Complete_First_Season_4_Discs_DVD', [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], .23),
    'cranium': ('Hasbro_Cranium_Performance_and_Acting_Game', [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], .60),
    'trivial': ('Hasbro_Trivial_Pursuit_Family_Edition_Game', [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], .80),
    'ouija': ('Supernatural_Ouija_Board_Game', [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], .75),
}


def read_source(path, name, rotation):
    verts, uvs, faces, uvfaces = [], [], [], []
    for line in path.read_text().splitlines():
        bits = line.split()
        if not bits:
            continue
        if bits[0] == 'v':
            verts.append([float(v) for v in bits[1:4]])
        elif bits[0] == 'vt':
            uvs.append([float(v) for v in bits[1:3]])
        elif bits[0] == 'f':
            faces.append([int(s.split('/')[0]) - 1 for s in bits[1:]])
            uvfaces.append([int(s.split('/')[1]) - 1 for s in bits[1:]])
    verts = np.array(verts)
    centre = (verts.min(0) + verts.max(0)) / 2
    verts = (verts - centre) @ np.array(rotation).T
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts.tolist(), [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name='UVMap')
    for face, indices in zip(mesh.polygons, uvfaces):
        for li, index in zip(face.loop_indices, indices):
            layer.data[li].uv = uvs[index]
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    mat = bpy.data.materials.new(name + '_source')
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path.parent / 'texture.png'), check_existing=True)
    mat.node_tree.links.new(tex.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    mesh.materials.append(mat)
    return obj, verts, centre


def geometry_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(np.asarray(verts).tolist(), [], np.asarray(faces).tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    return obj


def export_shape(obj, key):
    obj.data.calc_loop_triangles()
    vertices = np.array([list(v.co) for v in obj.data.vertices])
    triangles = np.array([list(t.vertices) for t in obj.data.loop_triangles], dtype=np.int32)
    filename = key + '.npz'
    np.savez_compressed(OUT / filename, vertices=vertices, triangles=triangles)
    return {'mesh_file': str(OUT / filename), 'vertices': len(vertices), 'triangles': len(triangles),
            'shape_sha256': hashlib.sha256(vertices.astype('<f8').tobytes() + triangles.astype('<i4').tobytes()).hexdigest(),
            'min': vertices.min(0).tolist(), 'max': vertices.max(0).tolist()}


def assign_nearest_uv(source, target):
    mesh = source.data
    mesh.calc_loop_triangles()
    verts = [Vector(v.co) for v in mesh.vertices]
    triangles = list(mesh.loop_triangles)
    tree = BVHTree.FromPolygons(verts, [list(t.vertices) for t in triangles], all_triangles=True)
    source_uv = mesh.uv_layers.active
    if source_uv is None:
        raise RuntimeError('missing source UV: ' + source.name)
    layer = target.data.uv_layers.new(name='UVMap')
    for mat in mesh.materials:
        target.data.materials.append(mat)
    max_deviation = 0.
    for poly in target.data.polygons:
        # One source triangle per target face prevents UV seams jumping midway
        # across a small target triangle. Shape and own material remain separate.
        hit, normal, ti, distance = tree.find_nearest(poly.center)
        if hit is None:
            raise RuntimeError('UV projection missed')
        triangle = triangles[ti]
        pts = [verts[i] for i in triangle.vertices]
        tex = [Vector((*source_uv.data[li].uv, 0.)) for li in triangle.loops]
        poly.material_index = triangle.material_index
        for li in poly.loop_indices:
            point = target.data.vertices[target.data.loops[li].vertex_index].co
            projected = barycentric_transform(point, *pts, *tex)
            layer.data[li].uv = projected.xy
            nearest = tree.find_nearest(point)
            max_deviation = max(max_deviation, nearest[3])
    return max_deviation


def make_box(key, dims):
    vertices = np.array([[x, y, z] for x in [-1., 1.] for y in [-1., 1.] for z in [-1., 1.]]) * dims / 2
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    obj = geometry_object('v63_asset_' + key, vertices, faces)
    layer = obj.data.uv_layers.new(name='UVMap')
    for face_index, poly in enumerate(obj.data.polygons):
        axis = int(np.argmax(np.abs(poly.normal)))
        axes = [i for i in range(3) if i != axis]
        col, row = face_index % 3, face_index // 3
        for li in poly.loop_indices:
            point = obj.data.vertices[obj.data.loops[li].vertex_index].co
            u, v = [point[a] / dims[a] + .5 for a in axes]
            layer.data[li].uv = ((col + .02 + .96 * u) / 3, (row + .02 + .96 * v) / 2)
    return obj


for key, (asset, rotation, mass) in SPECS.items():
    source, verts, centre = read_source(INPUT / asset / 'visual_geometry.obj', '__source_' + key, rotation)
    dims = np.ptp(verts, axis=0)
    target = make_box(key, dims)
    img = bpy.data.images.new(key + '_own_atlas', 2048, 2048, alpha=False)
    mat = bpy.data.materials.new(key + '_own_baked')
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = .55
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
    tex.image = img
    mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    mat.node_tree.nodes.active = tex
    target.data.materials.append(mat)
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.cage_extrusion = .025
    scene.render.bake.max_ray_distance = .07
    scene.render.bake.margin = 16
    bpy.ops.object.select_all(action='DESELECT')
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.bake(type='DIFFUSE', use_clear=True)
    image_path = OUT / 'textures' / (key + '_own_atlas.png')
    img.filepath_raw = str(image_path)
    img.file_format = 'PNG'
    img.save()
    pixels = np.empty(2048 * 2048 * 4, dtype=np.float32)
    img.pixels.foreach_get(pixels)
    rgb = pixels.reshape((-1, 4))[:, :3]
    stats = {'std': float(rgb.std()), 'nonzero_fraction': float((rgb.max(1) > .02).mean())}
    if stats['std'] < .01 or stats['nonzero_fraction'] < .5:
        raise RuntimeError('texture transfer failed: ' + key + ' ' + str(stats))
    assets[key] = {'asset_id': asset, 'object': target.name, 'dims': dims.tolist(), 'mass_estimate_kg': mass,
                   'mass_note': 'estimated, not measured; sensitivity required',
                   'source_centre': centre.tolist(), 'source_to_body': rotation,
                   'texture': str(image_path), 'texture_stats': stats,
                   'geometry_note': 'common box; scan chamfers/dents are not preserved', **export_shape(target, key)}
    source.hide_render = target.hide_render = True
    source.hide_set(True)
    target.hide_set(True)
    outputs.append(target)
    print('BOX_BAKED', key, stats, flush=True)

# Same recovered source mesh/materials; the shared convex surface is the one
# actually submitted to the probe solver, not a slightly larger scanned shell.
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ROOT / 'models/asset_recovery/v63/sphere_baseball/20261006_original4k/baseball_01_4k.gltf'))
imported = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
if len(imported) != 1:
    raise RuntimeError('baseball source expected one mesh')
source = imported[0]
source.data.transform(source.matrix_world)
source.matrix_world = Matrix.Identity(4)
centre = (np.array([list(v.co) for v in source.data.vertices]).min(0) + np.array([list(v.co) for v in source.data.vertices]).max(0)) / 2
source.data.transform(Matrix.Translation(Vector(-centre)))
ball = np.load(PROBE / 'baseball_common_hull.npz')
# Trimesh reads glTF Y-up, Blender converts to Z-up. Return the imported visual
# source to the exact probe body frame; do not rotate only the visible hull.
gltf_to_blender = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])
source.data.transform(Matrix(gltf_to_blender.T).to_4x4())
target = geometry_object('v63_asset_baseball', ball['vertices'], ball['triangles'])
deviation = assign_nearest_uv(source, target)
for face in target.data.polygons:
    face.use_smooth = True
assets['baseball'] = {'asset_id': 'sphere_baseball', 'object': target.name, 'mass_estimate_kg': .145,
                      'source': 'https://polyhaven.com/a/baseball_01', 'license': 'CC0-1.0',
                      'visual_import_to_body': gltf_to_blender.T.tolist(), 'uv_projection_max_vertex_distance_m': deviation,
                      'geometry_note': 'common convex hull; rigid approximation, no geometric displacement',
                      **export_shape(target, 'baseball')}
source.hide_render = target.hide_render = True
source.hide_set(True)
target.hide_set(True)
outputs.append(target)
print('BASEBALL_COMMON', deviation, flush=True)

# Ring sectors preserve the inner opening. Both consumers use these very same
# convex wedges; internal adjacent sector boundaries add no visible outer volume.
source, verts, centre = read_source(INPUT / 'Shurtape_30_Day_Removal_UV_Delct_15/visual_geometry.obj',
                                     '__source_tape', [[1, 0, 0], [0, 0, -1], [0, 1, 0]])
radius = float(np.ptp(verts[:, [0, 2]], axis=0).mean() / 2)
width = float(np.ptp(verts[:, 1]))
radial = np.linalg.norm(verts[:, [0, 2]], axis=1)
inner = float(np.percentile(radial, 3))
if not (.02 < inner < radius - .007):
    raise RuntimeError('unreliable measured tape opening')
parts = []
faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
for i in range(48):
    angles = [2 * math.pi * i / 48, 2 * math.pi * (i + 1) / 48]
    vv = [[r * math.cos(a), y, r * math.sin(a)] for r in [inner, radius] for y in [-width / 2, width / 2] for a in angles]
    obj = geometry_object('v63_asset_tape_%02d' % i, vv, faces)
    deviation = assign_nearest_uv(source, obj)
    parts.append({'object': obj.name, 'uv_projection_max_vertex_distance_m': deviation,
                  **export_shape(obj, 'tape_%02d' % i)})
    obj.hide_render = True
    obj.hide_set(True)
    outputs.append(obj)
source.hide_render = True
source.hide_set(True)
assets['tape'] = {'asset_id': 'Shurtape_30_Day_Removal_UV_Delct_15', 'outer_radius': radius,
                 'inner_radius': inner, 'width': width, 'parts': parts, 'mass_estimate_kg': .15,
                 'geometry_note': '48 common convex ring wedges, source appearance projected, hole retained'}
print('TAPE_COMMON', radius, inner, width, flush=True)

# Native radio: preserve its original materials and placement; the component
# convex surfaces match the probe. The author source file is only library-read.
with bpy.data.libraries.load(str(ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'), link=False) as (src, dst):
    dst.objects = ['boombox.002']
source = dst.objects[0]
scene.collection.objects.link(source)
radio_original = np.load(ROOT / 'log/V6.2_execution/geometry_audit/boombox.002.npz')
source.data = source.data.copy()
source.data.transform(Matrix(radio_original['matrix']))
radio_probe = json.loads((PROBE / 'summary.json').read_text())
radio_centre = np.array(radio_probe['radio_centre'])
source.data.transform(Matrix.Translation(Vector(-radio_centre)))
source.matrix_world = Matrix.Identity(4)
parts = []
for i in range(radio_probe['radio_common_parts']):
    part = np.load(PROBE / ('radio_common_%02d.npz' % i))
    obj = geometry_object('v63_asset_radio_%02d' % i, part['vertices'], part['triangles'])
    deviation = assign_nearest_uv(source, obj)
    parts.append({'object': obj.name, 'uv_projection_max_vertex_distance_m': deviation,
                  **export_shape(obj, 'radio_%02d' % i)})
    obj.hide_render = True
    obj.hide_set(True)
    outputs.append(obj)
source.hide_render = True
source.hide_set(True)
assets['radio'] = {'asset_id': 'boombox.002', 'parts': parts, 'initial_centre': radio_centre.tolist(),
                  'mass_estimate_kg': 1.5, 'geometry_note': '37 common component hulls; source materials/pose retained, not soft antenna'}
print('RADIO_COMMON', len(parts), flush=True)

with (OUT / 'manifest.json').open('x') as handle:
    json.dump({'status': 'COMMON_ASSETS_PENDING_VISUAL_QA', 'assets': assets}, handle, indent=2)
bpy.data.libraries.write(str(OUT / 'common_assets.blend'), set(outputs), path_remap='ABSOLUTE', fake_user=True)
print('COMMON_ASSETS_COMPLETE', flush=True)
