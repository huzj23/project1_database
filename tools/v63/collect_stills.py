"""Incremental SFTP delivery of complete, device-checked PNGs, no overwrite."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys

LOCAL = Path(r'D:\workspace\project1_database')
spec = importlib.util.spec_from_file_location('project_remote', LOCAL / 'tools/v62/remote_ops.py')
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)
password = os.environ.pop('PROJECT1_CHENLIANG_SSH_PASSWORD')
client = remote.paramiko.SSHClient()
client.set_missing_host_key_policy(remote.ProjectHostPolicy())
client.connect('172.16.30.12', username='chenliang', password=password, timeout=15,
               allow_agent=False, look_for_keys=False)
password = None
batch = sys.argv[1] if len(sys.argv) > 1 else 'r1'
assert batch in ('r1', 'r2', 'r3')
folder = remote.REMOTE + '/tmp/v63_node12/static_gpu_' + batch
out = LOCAL / 'outcomes/v63/radio_scurve_domino/20261006_static_review'
out.mkdir(parents=True, exist_ok=True)
collected = []
try:
    with client.open_sftp() as sftp:
        remote.remote_checked(sftp, folder)
        for entry in sorted(sftp.listdir_attr(folder), key=lambda a: a.filename):
            if not entry.filename.endswith('_render.json'):
                continue
            with sftp.open(folder + '/' + entry.filename, 'r') as handle:
                record = json.load(handle)
            ident = record['id']
            if record['status'] != 'RENDERED_PENDING_VISUAL_QA':
                raise RuntimeError('not a completed frame')
            contexts = record['devices']['observed_contexts']
            if contexts != ['GPU-665e9626-9862-7424-fc4a-dc90d61079fa'] or record['devices']['other_pids']:
                raise RuntimeError('unverified GPU use')
            target_dir = out
            if batch == 'r1' and ident in ('04_drop_bridge', '10_follow_camera_sample'):
                target_dir = out / 'earlier_camera_crop_revision'
            target_dir.mkdir(parents=True, exist_ok=True)
            for filename in (ident + '.png', entry.filename):
                target = target_dir / filename
                source = remote.remote_checked(sftp, folder + '/' + filename)
                if target.exists():
                    if target.stat().st_size != sftp.stat(source).st_size:
                        raise RuntimeError('existing local artifact differs; no overwrite')
                    continue
                sftp.get(source, str(target))
            digest = hashlib.sha256((target_dir / (ident + '.png')).read_bytes()).hexdigest()
            collected.append({'id': ident, 'path': str(target_dir / (ident + '.png')),
                              'sha256': digest, 'render_seconds': record['seconds']})
    print(json.dumps({'complete_images': collected}, ensure_ascii=False, indent=2))
finally:
    client.close()
