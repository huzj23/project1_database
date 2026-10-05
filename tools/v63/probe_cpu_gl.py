"""Tiny offscreen software-OpenGL test, no CUDA devices, no source scene."""
from pathlib import Path
import json
import os
import bpy
import gpu

OUT = Path('/data/raw/huzijian/project1_database/tmp/v63_node12/cpu_gl_probe_r3')
OUT.mkdir(parents=True, exist_ok=False)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 32
scene.render.resolution_y = 32
scene.render.resolution_percentage = 100
scene.render.threads_mode = 'FIXED'
scene.render.threads = 8
scene.render.filepath = str(OUT / 'software_test.png')
bpy.ops.render.render(write_still=True)
report = {'renderer': gpu.platform.renderer_get(), 'vendor': gpu.platform.vendor_get(),
          'version': gpu.platform.version_get(), 'pid': os.getpid(),
          'cuda_visible': os.environ.get('CUDA_VISIBLE_DEVICES'),
          'egl_vendor_manifest': os.environ.get('__EGL_VENDOR_LIBRARY_FILENAMES')}
if 'llvmpipe' not in report['renderer'].lower():
    raise RuntimeError('refuse non-software GL backend: ' + str(report))
with (OUT / 'report.json').open('x') as handle:
    json.dump(report, handle, indent=2)
print('CPU_GL_PROVEN', json.dumps(report), flush=True)
