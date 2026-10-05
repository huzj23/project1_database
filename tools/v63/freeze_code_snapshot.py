"""Clone a local Git bundle to a NEW isolated in-workspace server checkout."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess

ROOT = Path('/data/raw/huzijian/project1_database')
ap = argparse.ArgumentParser()
ap.add_argument('--bundle', required=True)
ap.add_argument('--commit', required=True)
ap.add_argument('--revision', required=True)
args = ap.parse_args()
bundle = Path(args.bundle).resolve()
assert ROOT in bundle.parents
assert len(args.commit) == 40 and all(c in '0123456789abcdef' for c in args.commit)
assert re.fullmatch(r'r[1-9][0-9]*', args.revision)
snapshot_name = 'v63_' + args.commit[:12] + '_' + args.revision
out = ROOT / 'code_snapshots' / snapshot_name
if out.exists():
    raise RuntimeError('refuse checkout overwrite')
env = dict(os.environ)
env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': str(ROOT / 'tools/v63/gitconfig'),
            'GIT_TEMPLATE_DIR': str(ROOT / 'tmp/v63_node11/git_empty_template')})
Path(env['GIT_TEMPLATE_DIR']).mkdir(parents=True, exist_ok=True)
# Bundles need not advertise HEAD. Older server Git also lacks the -C option.
subprocess.run(['/usr/bin/git', 'clone', '--branch', 'main', '--no-hardlinks', str(bundle), str(out)], check=True, env=env)
git = ['/usr/bin/git', '--git-dir=' + str(out / '.git'), '--work-tree=' + str(out)]
actual = subprocess.check_output(git + ['rev-parse', 'HEAD'], env=env, text=True).strip()
if actual != args.commit:
    raise RuntimeError('snapshot commit mismatch')
subprocess.run(git + ['remote', 'set-url', 'origin',
                'https://github.com/huzj23/project1_database.git'], env=env, check=True)
with (ROOT / 'log/V6.3_execution' / ('server_snapshot_' + args.commit[:12] + '_' + args.revision + '.json')).open('x') as handle:
    json.dump({'commit': actual, 'checkout': str(out), 'bundle': str(bundle),
               'root_worktree_modified': False, 'remote': 'https://github.com/huzj23/project1_database.git'}, handle, indent=2)
print('SERVER_CODE_SNAPSHOT', actual, str(out), flush=True)
