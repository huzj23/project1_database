"""Download only this task's code/evidence; never overwrite or inspect secrets."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import stat
import sys

LOCAL = Path(r'D:\workspace\project1_database')
spec = importlib.util.spec_from_file_location('project_remote', LOCAL / 'tools/v62/remote_ops.py')
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)
password = os.environ.pop('PROJECT1_WANGZILE_SSH_PASSWORD')
client = remote.paramiko.SSHClient()
client.set_missing_host_key_policy(remote.ProjectHostPolicy())
client.connect('172.16.30.11', username='wangzile', password=password, timeout=15,
               allow_agent=False, look_for_keys=False)
password = None
destination = LOCAL / 'tools/v63/server_history/20261006_r2'
prior = LOCAL / 'tools/v63/server_history/20261006_r1'
destination.mkdir(parents=True, exist_ok=False)
records = []
try:
    with client.open_sftp() as sftp:
        folder = remote.remote_checked(sftp, remote.REMOTE + '/tools/v63')
        for entry in sorted(sftp.listdir_attr(folder), key=lambda a: a.filename):
            if not stat.S_ISREG(entry.st_mode) or Path(entry.filename).suffix not in ('.py', '.sh', '.c'):
                continue
            if (prior / entry.filename).exists():
                if (prior / entry.filename).stat().st_size != entry.st_size:
                    raise RuntimeError('immutable server history changed unexpectedly')
                continue
            if entry.st_size > 200000:
                raise ValueError('unexpected code size')
            source = remote.remote_checked(sftp, folder + '/' + entry.filename)
            target = destination / entry.filename
            sftp.get(source, str(target))
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            records.append({'remote': source, 'local': str(target), 'bytes': target.stat().st_size, 'sha256': digest})
    with (destination / 'BACKUP_MANIFEST.json').open('x', encoding='utf8') as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'files': len(records), 'destination': str(destination)}))
finally:
    client.close()
