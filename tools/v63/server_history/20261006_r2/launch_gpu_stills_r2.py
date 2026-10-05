"""Idle-only UUID-bound EEVEE, CPU Cycles, all outputs inside the workspace."""
from pathlib import Path
import json
import os
import subprocess
import shutil
import time
import xml.etree.ElementTree as ET

ROOT = Path('/data/raw/huzijian/project1_database')
UUID = 'GPU-665e9626-9862-7424-fc4a-dc90d61079fa'
CONTROL = ROOT / 'tmp/v63_node12/gpu_static_control_r2'
CONTROL.mkdir(parents=True, exist_ok=False)
previous_log = ROOT / 'tmp/v63_node12/gpu_static_control_r1.log'
deadline = time.monotonic() + 2400
while True:
    previous = previous_log.read_text() if previous_log.exists() else ''
    if 'SCOPED_STILLS_EXIT 0' in previous:
        break
    if 'SCOPED_STILLS_EXIT' in previous or time.monotonic() > deadline:
        raise RuntimeError('previous task batch failed or did not finish; no overlap')
    time.sleep(10)
proof = json.loads((ROOT / 'tmp/v63_node12/gpu_scope_probe_r2/verified_device.json').read_text())
assert proof['actual_gpu_contexts'] and all(row['uuid'] == UUID for row in proof['actual_gpu_contexts'])
snapshots = []
for attempt in range(2):
    tree = ET.fromstring(subprocess.check_output(['/usr/bin/nvidia-smi', '-i', UUID, '-q', '-x'], text=True))
    gpu = tree.find('gpu')
    memory = int(gpu.findtext('fb_memory_usage/used').split()[0])
    utilization = int(gpu.findtext('utilization/gpu_util').split()[0])
    count = len(gpu.findall('.//process_info'))
    snapshots.append({'time': time.time(), 'uuid': gpu.findtext('uuid'), 'memory_mb': memory,
                      'utilization': utilization, 'process_count': count})
    if gpu.findtext('uuid') != UUID or memory >= 128 or utilization > 1 or count:
        with (CONTROL / 'refused.json').open('x') as handle:
            json.dump(snapshots, handle, indent=2)
        raise RuntimeError('GPU no longer idle')
    if attempt == 0:
        time.sleep(5)
with (CONTROL / 'idle_snapshots.json').open('x') as handle:
    json.dump(snapshots, handle, indent=2)
env = dict(os.environ)
env.pop('CUDA_VISIBLE_DEVICES', None)
env.pop('CUDA_DEVICE_ORDER', None)
env.update({'V63_GPU_UUID': UUID,
            'V62_SCRATCH': str(CONTROL / 'scratch'),
            'LD_PRELOAD': str(ROOT / 'tools/runtime/v63_egl_uuid_r1/libv63_egl_uuid_r2.so'),
            '__EGL_VENDOR_LIBRARY_FILENAMES': str(ROOT / 'tools/runtime/v63_egl_uuid_r1/nvidia_vendor.json')})
old_cache = ROOT / 'tmp/v63_node12/gpu_static_control_r1/scratch/gl_shader_cache'
if old_cache.is_dir():
    # Preserve the old cache and seed a fresh project-scoped cache, not a global
    # driver cache. No old output/image is touched.
    shutil.copytree(old_cache, CONTROL / 'scratch/gl_shader_cache')
ids = ['04_drop_bridge', '10_follow_camera_sample']
argv = ['/bin/bash', '--noprofile', '--norc', str(ROOT / 'tools/v62/blender42_scoped.sh'),
        '--background', '--factory-startup', '--disable-autoexec', '--threads', '16',
        '--python-exit-code', '2', '--python', str(ROOT / 'tools/v63/render_static_r2.py'), '--',
        '--scene-dir', str(ROOT / 'tmp/v63_node11/static_scene_r4'),
        '--out', str(ROOT / 'tmp/v63_node12/static_gpu_r2'), '--ids', ','.join(ids)]
with (CONTROL / 'blender.log').open('x') as handle:
    result = subprocess.run(argv, env=env, stdout=handle, stderr=subprocess.STDOUT)
print('SCOPED_STILLS_EXIT', result.returncode, flush=True)
raise SystemExit(result.returncode)
