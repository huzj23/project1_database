"""Read-only system resource metadata and only this task's tmux process tree."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path('/data/raw/huzijian/project1_database')
node = sys.argv[1]
assert node in ('11', '12')
out = ROOT / ('tmp/v63_node' + node) / 'render_resources_r1.json'
socket = ROOT / 'tmp' / ('v63_node%s_control.sock' % node)


def run(args):
    cp = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return {'rc': cp.returncode, 'stdout': cp.stdout, 'stderr': cp.stderr}


panes = run(['/usr/bin/tmux', '-S', str(socket), 'list-panes', '-t', 'v63_stills_r1',
             '-F', '#{pane_pid} #{pane_dead}'])
pids = []
if panes['rc'] == 0:
    pids = [int(line.split()[0]) for line in panes['stdout'].splitlines()]
    frontier = list(pids)
    for _ in range(4):
        following = []
        for pid in frontier:
            child = run(['/usr/bin/ps', '--ppid', str(pid), '-o', 'pid='])
            following += [int(s) for s in child['stdout'].split()]
        pids += following
        frontier = following
result = {'time': time.time(), 'load': os.getloadavg(), 'panes': panes,
          'task_processes': run(['/usr/bin/ps', '-p', ','.join(map(str, pids)),
                                 '-o', 'pid,ppid,pcpu,pmem,rss,etime,time,stat,comm']) if pids else None,
          'gpus': run(['/usr/bin/nvidia-smi', '--query-gpu=index,uuid,memory.used,utilization.gpu',
                       '--format=csv,noheader,nounits']),
          'gpu_processes': run(['/usr/bin/nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory',
                                '--format=csv,noheader'])}
with out.open('x') as handle:
    json.dump(result, handle, indent=2)
print(json.dumps(result, indent=2), flush=True)
