"""Tiny authorized-device smoke render, not the full authored scene."""
from pathlib import Path
import json
import os
import subprocess
import bpy
import gpu

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'tmp/v63_node12/gpu_scope_probe_r1'
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
scene.render.engine = 'CYCLES'
scene.cycles.samples = 2
scene.cycles.device = 'GPU'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.get_devices()
enabled = []
for d in prefs.devices:
    d.use = d.type == 'CUDA'
    if d.use:
        enabled.append({'name': d.name, 'id': d.id})
if len(enabled) != 1:
    raise RuntimeError('CUDA isolation failed')
scene.render.filepath = str(OUT / 'cuda_test.png')
bpy.ops.render.render(write_still=True)
device['cuda'] = enabled
device['nvidia_process_snapshot'] = subprocess.check_output(
    ['/usr/bin/nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory',
     '--format=csv,noheader'], text=True)
ours = [line for line in device['nvidia_process_snapshot'].splitlines()
        if line.split(',')[0].strip() == str(os.getpid())]
if not ours or any(os.environ['V63_GPU_UUID'] not in line for line in ours):
    raise RuntimeError('actual process GPU mismatch')
with (OUT / 'verified_device.json').open('x') as handle:
    json.dump(device, handle, indent=2)
print('GPU_SCOPE_VERIFIED', device, flush=True)
