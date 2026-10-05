"""Only system resource metadata; output exclusively inside the project."""
from pathlib import Path
import json
import os
import platform
import subprocess
import sys
import time

root = Path('/data/raw/huzijian/project1_database')
target = Path(sys.argv[1]).resolve()
if root not in target.parents:
    raise ValueError('outside workspace')
rows = {}
for key, argv in {
    'gpu': ['/usr/bin/nvidia-smi', '--query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'],
    'processes': ['/usr/bin/nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory', '--format=csv,noheader'],
    'memory': ['/usr/bin/free', '-m'],
}.items():
    p = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    rows[key] = {'rc': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
data = {'epoch': time.time(), 'hostname': platform.node(), 'load': os.getloadavg(),
        'cpu_count': os.cpu_count(), 'resources': rows}
target.parent.mkdir(parents=True, exist_ok=True)
with target.open('x', encoding='utf8') as handle:
    json.dump(data, handle, indent=2)
print(json.dumps(data, indent=2), flush=True)
