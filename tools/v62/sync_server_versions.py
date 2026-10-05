"""Back up exact task-script versions from the authorized server workspace."""
import hashlib
import json
import os
from pathlib import Path
import paramiko
from remote_ops import ProjectHostPolicy, remote_checked, LOCAL, REMOTE

password = os.environ.pop('PROJECT1_WANGZILE_SSH_PASSWORD')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(ProjectHostPolicy())
client.connect('172.16.30.11', username='wangzile', password=password,
               allow_agent=False, look_for_keys=False, timeout=15, auth_timeout=15)
password = None
names = ['server_probe.py','server_probe_v2.py','inspect_source.py','inspect_source_v2.py',
         'prepare_compat_runtime.py','prepare_compat_runtime_r2.py', 'blender42.sh',
         'pilot_render.py','pilot_render_r2.py','pilot_render_r3.py','pilot_render_r4.py',
         'mechanism_probe.py','mechanism_probe_r2.py','mechanism_probe_r3.py']
destination = LOCAL / 'tools/v62/server_history'
destination.mkdir(parents=True, exist_ok=True)
manifest = []
try:
    with client.open_sftp() as sftp:
        for name in names:
            source = remote_checked(sftp, REMOTE+'/tools/v62/'+name)
            with sftp.open(source,'rb') as stream:
                data = stream.read(128*1024)
            target = destination/name
            with target.open('xb') as f:
                f.write(data)
            manifest.append({'remote':source,'local':str(target),'bytes':len(data),
                             'sha256':hashlib.sha256(data).hexdigest()})
    with (destination/'manifest.json').open('x',encoding='utf-8') as f:
        json.dump(manifest,f,indent=2)
    print(json.dumps({'backed_up':len(manifest),'directory':str(destination)}))
finally:
    client.close()
