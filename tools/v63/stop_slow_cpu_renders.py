"""Stop only verified V6.3 software-render children; retain every file/log."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys

ROOT = Path('/data/raw/huzijian/project1_database')
node = sys.argv[1]
assert node in ('11', '12')
socket = ROOT / 'tmp' / ('v63_node%s_control.sock' % node)
targets = [('v63_stills_r1', ROOT / ('tmp/v63_node%s/static_render_r1' % node))]
if node == '12':
    targets.append(('v63_still_nopt_r1', ROOT / 'tmp/v63_node12/static_render_nopt_r1'))
records = []
for session, expected_out in targets:
    cp = subprocess.run(['/usr/bin/tmux', '-S', str(socket), 'list-panes', '-t', session,
                         '-F', '#{pane_pid} #{pane_dead}'], capture_output=True, text=True)
    if cp.returncode:
        records.append({'session': session, 'status': 'NO_SESSION'})
        continue
    shellpid, dead = cp.stdout.split()
    if dead == '1':
        records.append({'session': session, 'status': 'ALREADY_ENDED'})
        continue
    children = subprocess.check_output(['/usr/bin/ps', '--ppid', shellpid, '-o', 'pid='], text=True).split()
    for child in children:
        command = subprocess.check_output(['/usr/bin/ps', '-p', child, '-o', 'args='], text=True).strip()
        expected = str(ROOT / 'tools/v63/render_static_r1.py')
        if expected not in command or ('--out ' + str(expected_out) + ' ') not in command:
            raise RuntimeError('refuse unrelated process termination')
        os.kill(int(child), signal.SIGTERM)
        records.append({'session': session, 'pid': int(child), 'verified_command': command,
                        'status': 'SIGTERM_OWN_RENDER_ONLY', 'files_deleted': False})
out = ROOT / ('tmp/v63_node%s/stopped_cpu_renders_r1.json' % node)
with out.open('x') as handle:
    json.dump(records, handle, indent=2)
print(json.dumps(records, indent=2))
