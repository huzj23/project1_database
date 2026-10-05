"""Tiny authorized-device smoke render, not the full authored scene."""
from pathlib import Path
import json
import os
import subprocess
import bpy
import gpu

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node12/gpu_scope_probe_r2'
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.eevee.taa_render_samples = 2
scene.render.resolution_x = scene.render.resolution_y = 32
scene.render.resolution_percentage = 100
scene.render.filepath = str(OUT / 'egl_test.png')
bpy.ops.render.render(write_still=True)
device = {'renderer': gpu.platform.renderer_get(), 'vendor': gpu.platform.vendor_get(),
          'version': gpu.platform.version_get(), 'uuid_required': os.environ['V63_GPU_UUID'],
          'pid': os.getpid()}
if 'NVIDIA' not in device['vendor']:
    raise RuntimeError('unexpected EGL driver')
import xml.etree.ElementTree as ET
snapshot = ET.fromstring(subprocess.check_output(['/usr/bin/nvidia-smi', '-q', '-x'], text=True))
ours = []
for card in snapshot.findall('gpu'):
    for proc in card.findall('.//process_info'):
        if proc.findtext('pid') == str(os.getpid()):
            ours.append({'uuid': card.findtext('uuid'), 'type': proc.findtext('type'),
                         'memory': proc.findtext('used_memory')})
device['actual_gpu_contexts'] = ours
with (OUT / 'observed_device.json').open('x') as handle:
    json.dump(device, handle, indent=2)
if not ours or any(row['uuid'] != os.environ['V63_GPU_UUID'] for row in ours):
    raise RuntimeError('actual graphics context GPU mismatch')
with (OUT / 'verified_device.json').open('x') as handle:
    json.dump(device, handle, indent=2)
print('GPU_SCOPE_VERIFIED', device, flush=True)
