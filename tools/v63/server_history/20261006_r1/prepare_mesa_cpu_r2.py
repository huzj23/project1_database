"""Isolated CPU Mesa runtime, official SHA-checked packages, no system install.

No maintainer scripts are run. Only runtime libraries are extracted. This lets
authored EEVEE fog use software OpenGL without touching busy NVIDIA devices.
"""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import lzma
import os
import re
import ssl
import tarfile
import urllib.request

ROOT = Path('/data/raw/huzijian/project1_database')
DEST = ROOT / 'tools/runtime/v63_mesa_cpu_r2'
INDEX = 'https://deb.debian.org/debian/dists/bullseye/main/binary-amd64/Packages.xz'


def fetch(url, sha=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'Project1-scoped-runtime/6.3'})
    context = ssl.create_default_context(cafile=str(ROOT / 'tools/runtime/ca-bundle.crt'))
    errors = []
    blob = None
    for proxy in [{}, {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}]:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxy), urllib.request.HTTPSHandler(context=context))
        try:
            with opener.open(req, timeout=35) as response:
                blob = response.read(128 * 1024 * 1024)
            break
        except Exception as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
    if blob is None:
        raise RuntimeError('official runtime download failed: ' + repr(errors))
    if sha and hashlib.sha256(blob).hexdigest() != sha:
        raise ValueError('package checksum failure')
    return blob


def data_tar(blob):
    if blob[:8] != b'!<arch>\n':
        raise ValueError('not Debian ar archive')
    pos = 8
    while pos + 60 <= len(blob):
        head = blob[pos:pos + 60]
        size = int(head[48:58].decode().strip())
        name = head[:16].decode().strip().rstrip('/')
        if name.startswith('data.tar'):
            return blob[pos + 60:pos + 60 + size]
        pos += 60 + size + size % 2
    raise ValueError('no data archive')


def main():
    os.umask(0o022)
    DEST.mkdir(parents=True, exist_ok=False)
    lib = DEST / 'lib'
    lib.mkdir()
    index_blob = fetch(INDEX)
    blocks = lzma.decompress(index_blob).decode('utf8').split('\n\n')
    packages = {}
    for block in blocks:
        meta = dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line and not line.startswith(' '))
        if 'Package' in meta:
            packages[meta['Package']] = meta
    queue = ['libegl1', 'libegl-mesa0', 'libgl1-mesa-dri', 'libglx0', 'libopengl0']
    # Compatible copies already exist in the task's explicit loader search path.
    skip = {'libc6', 'libgcc-s1', 'libstdc++6', 'debconf', 'debconf-2.0', 'libsensors-config'}
    done, links, rows = set(), [], []
    while queue:
        name = queue.pop(0)
        if name in done or name in skip:
            continue
        if name not in packages:
            raise ValueError('unresolved runtime dependency: ' + name)
        done.add(name)
        meta = packages[name]
        for dep in meta.get('Depends', '').split(','):
            if dep.strip():
                queue.append(re.split(r'[\s(:]', dep.strip().split('|')[0].strip())[0])
        blob = fetch('https://deb.debian.org/debian/' + meta['Filename'], meta['SHA256'])
        with (DEST / Path(meta['Filename']).name).open('xb') as handle:
            handle.write(blob)
        names = []
        with tarfile.open(fileobj=io.BytesIO(data_tar(blob)), mode='r:*') as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                normalized = str(path)
                prefixes = ['usr/lib/x86_64-linux-gnu/', 'lib/x86_64-linux-gnu/']
                prefix = next((v for v in prefixes if normalized.startswith(v)), None)
                if prefix is None:
                    continue
                relative = PurePosixPath(normalized[len(prefix):])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('unsafe archive member')
                # Only the software DRI driver, never hardware-driver plugins.
                if len(relative.parts) > 1 and str(relative) not in ['dri/swrast_dri.so', 'dri/kms_swrast_dri.so']:
                    continue
                if '.so' not in relative.name:
                    continue
                target = lib / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if member.isfile():
                    with archive.extractfile(member) as source:
                        data = source.read()
                    if target.exists():
                        if target.read_bytes() != data:
                            raise ValueError('runtime collision: ' + str(target))
                    else:
                        with target.open('xb') as handle:
                            handle.write(data)
                        target.chmod(0o755)
                    names.append(str(relative))
                elif member.issym():
                    linked = PurePosixPath(member.linkname)
                    if linked.is_absolute() or len(linked.parts) != 1:
                        raise ValueError('nonlocal runtime symlink')
                    links.append((target, member.linkname))
        rows.append({'package': name, 'version': meta['Version'], 'url': 'https://deb.debian.org/debian/' + meta['Filename'],
                     'sha256': meta['SHA256'], 'files': names})
        print('RUNTIME_PACKAGE', name, len(blob), flush=True)
    for target, linked in links:
        if target.is_symlink():
            continue
        if not (target.parent / linked).is_file():
            raise ValueError('missing local link target: ' + str(target))
        target.symlink_to(linked)
    vendor = {'file_format_version': '1.0.0', 'ICD': {'library_path': str(lib / 'libEGL_mesa.so.0')}}
    for name, data in [('mesa_vendor.json', vendor), ('manifest.json', {'index': INDEX, 'index_sha256': hashlib.sha256(index_blob).hexdigest(), 'packages': rows, 'system_modified': False})]:
        with (DEST / name).open('x') as handle:
            json.dump(data, handle, indent=2)
    print('MESA_RUNTIME_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
