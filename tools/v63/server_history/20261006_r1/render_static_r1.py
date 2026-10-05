"""Render selected immutable V6.3 stills on CPU + explicitly software EGL."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import bpy
import gpu

ROOT = Path('/data/raw/huzijian/project1_database')
ap = argparse.ArgumentParser()
ap.add_argument('--scene-dir', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--ids', required=True)
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
scene_dir, out = Path(args.scene_dir).resolve(), Path(args.out).resolve()
assert ROOT in scene_dir.parents and ROOT in out.parents
out.mkdir(parents=True, exist_ok=False)
report = json.loads((scene_dir / 'composition_report.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(scene_dir / 'review_scene.blend'))
main = bpy.data.scenes['Scene']
bpy.context.window.scene = main
assert os.environ.get('CUDA_VISIBLE_DEVICES') == '-1'
rows = []
for ident in args.ids.split(','):
    specification = next(v for v in report['cameras'] if v['id'] == ident)
    camera = bpy.data.objects[specification['camera_object']]
    bindings = []
    for scene in bpy.data.scenes:
        scene.camera = camera
        scene.frame_set(1)
        if scene.render.engine == 'CYCLES':
            scene.cycles.device = 'CPU'
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 16
        if scene.use_nodes:
            for node in scene.node_tree.nodes:
                if node.type == 'OUTPUT_FILE':
                    node.base_path = str(out / ('compositor_' + ident + '_' + scene.name))
        bindings.append({'scene': scene.name, 'camera': camera.name, 'frame': scene.frame_current,
                         'resolution': [scene.render.resolution_x, scene.render.resolution_y,
                                        scene.render.resolution_percentage], 'engine': scene.render.engine,
                         'matrix': [list(r) for r in camera.matrix_world]})
    image_path = out / (ident + '.png')
    if image_path.exists():
        raise RuntimeError('refuse image overwrite')
    main.render.filepath = str(image_path)
    start = time.time()
    print('STATIC_START', ident, flush=True)
    bpy.ops.render.render(write_still=True, scene=main.name)
    device = {'renderer': gpu.platform.renderer_get(), 'vendor': gpu.platform.vendor_get(),
              'version': gpu.platform.version_get(), 'cycles_device': main.cycles.device,
              'cuda_visible': os.environ['CUDA_VISIBLE_DEVICES']}
    if 'llvmpipe' not in device['renderer'].lower():
        raise RuntimeError('Fog did not use proven software GL')
    row = {'id': ident, 'file': str(image_path), 'seconds': time.time() - start,
           'bindings': bindings, 'devices': device, 'status': 'RENDERED_PENDING_VISUAL_QA'}
    rows.append(row)
    with (out / (ident + '_render.json')).open('x') as handle:
        json.dump(row, handle, indent=2)
    print('STATIC_FINISHED', ident, row['seconds'], flush=True)
with (out / 'render_manifest.json').open('x') as handle:
    json.dump(rows, handle, indent=2)
