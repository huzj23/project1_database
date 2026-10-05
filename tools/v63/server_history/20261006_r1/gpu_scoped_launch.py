"""Require two idle snapshots for exactly one UUID; start only scoped Blender.

EGL and CUDA both select the same verified GPU UUID. No fallback device allowed.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path('/data/raw/huzijian/project1_database')
UUID = 'GPU-665e9626-9862-7424-fc4a-dc90d61079fa'
runtime = ROOT / 'tools/runtime/v63_egl_uuid_r1'
out = ROOT / 'tmp/v63_node12/gpu_scope_probe_r1'
runtime.mkdir(parents=True, exist_ok=True)
out.mkdir(parents=True, exist_ok=False)


def command(argv):
    return subprocess.check_output(argv, text=True, timeout=30)


snapshots = []
for attempt in range(2):
    gpu = command(['/usr/bin/nvidia-smi', '-i', UUID,
                   '--query-gpu=uuid,memory.used,utilization.gpu', '--format=csv,noheader,nounits'])
    processes = command(['/usr/bin/nvidia-smi', '-i', UUID,
                         '--query-compute-apps=pid', '--format=csv,noheader,nounits']).strip()
    fields = [v.strip() for v in gpu.split(',')]
    full = command(['/usr/bin/nvidia-smi', '-i', UUID, '-q', '-x'])
    import xml.etree.ElementTree as ET
    process_nodes = ET.fromstring(full).findall('.//process_info')
    snapshots.append({'gpu': gpu, 'processes': processes, 'all_process_count': len(process_nodes), 'time': time.time()})
    if fields[0] != UUID or int(fields[1]) >= 128 or int(fields[2]) > 1 or processes or process_nodes:
        with (out / 'resource_refusal.json').open('x') as handle:
            json.dump(snapshots, handle, indent=2)
        raise RuntimeError('selected GPU is not idle; refusing render')
    if attempt == 0:
        time.sleep(5)
with (out / 'idle_snapshots.json').open('x') as handle:
    json.dump(snapshots, handle, indent=2)
library = runtime / 'libv63_egl_uuid.so'
if not library.exists():
    subprocess.run(['/usr/bin/gcc', '-std=c99', '-fPIC', '-shared', '-O2',
                    str(ROOT / 'tools/v63/egl_uuid_scope.c'), '-o', str(library), '-ldl'], check=True)
vendor = runtime / 'nvidia_vendor.json'
if not vendor.exists():
    with vendor.open('x') as handle:
        json.dump({'file_format_version': '1.0.0', 'ICD': {'library_path': 'libEGL_nvidia.so.0'}}, handle)
environment = dict(os.environ)
environment.update({'CUDA_VISIBLE_DEVICES': UUID, 'V63_GPU_UUID': UUID,
                    'V62_SCRATCH': str(out / 'scratch'), 'LD_PRELOAD': str(library),
                    '__EGL_VENDOR_LIBRARY_FILENAMES': str(vendor)})
argv = ['/bin/bash', '--noprofile', '--norc', str(ROOT / 'tools/v62/blender42_scoped.sh'),
        '--background', '--factory-startup', '--disable-autoexec', '--threads', '8',
        '--python-exit-code', '2', '--python', str(ROOT / 'tools/v63/probe_gpu_scope.py')]
with (out / 'blender.log').open('x') as handle:
    result = subprocess.run(argv, env=environment, stdout=handle, stderr=subprocess.STDOUT)
print('GPU_SCOPE_PROBE_EXIT', result.returncode, flush=True)
raise SystemExit(result.returncode)
