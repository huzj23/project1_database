"""Fail closed unless the entire node is idle (EGL selection is not CUDA masking)."""
import json
import subprocess
import time

reports = []
for i in range(2):
    processes = subprocess.run(['/usr/bin/nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory',
                                '--format=csv,noheader'], capture_output=True, text=True, check=True)
    cards = subprocess.run(['/usr/bin/nvidia-smi', '--query-gpu=index,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
    idle = not processes.stdout.strip()
    for row in cards.stdout.strip().splitlines():
        _, _, mem, utilization = [v.strip() for v in row.split(',')]
        idle = idle and float(mem) < 128 and float(utilization) == 0
    reports.append({'epoch': time.time(), 'idle': idle, 'processes': processes.stdout, 'gpus': cards.stdout})
    if not idle:
        print(json.dumps(reports, indent=2))
        raise SystemExit('GPU resources occupied; refusing render')
    if i == 0:
        time.sleep(3)
print(json.dumps(reports, indent=2))
