"""Project-local Blender runtime loader, no system installation or environment changes.

Only vetted regular runtime files and relative symlinks from the official Debian
package are extracted. Its maintainer scripts are never run. The system libc and
the shared conda environment are not modified.
"""
from __future__ import annotations
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import ssl
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path('/data/raw/huzijian/project1_database')
DEST = ROOT / 'tools/runtime/v62_compat_debian231_r2'
INDEX_URL = 'https://deb.debian.org/debian/dists/bullseye/main/binary-amd64/Packages.xz'


def fetch(url, sha=None):
    context = ssl.create_default_context(cafile=str(ROOT / 'tools/runtime/ca-bundle.crt'))
    errors = []
    for proxy in [{}, {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}]:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxy),
                                            urllib.request.HTTPSHandler(context=context))
        try:
            with opener.open(url, timeout=25) as resp:
                data = resp.read(32 * 1024 * 1024)
            if sha and hashlib.sha256(data).hexdigest() != sha:
                raise RuntimeError('official package SHA256 mismatch')
            return data
        except Exception as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
    raise RuntimeError('download failed: ' + repr(errors))


def data_tar(blob):
    if blob[:8] != b'!<arch>\n':
        raise ValueError('not a Debian ar archive')
    pos = 8
    while pos + 60 <= len(blob):
        header = blob[pos:pos+60]
        size = int(header[48:58].decode().strip())
        name = header[:16].decode().strip().rstrip('/')
        content = blob[pos+60:pos+60+size]
        if name.startswith('data.tar'):
            return content
        pos += 60 + size + size % 2
    raise ValueError('no data archive')


def main():
    if DEST.exists():
        raise SystemExit('refuse overwrite of runtime trial')
    DEST.mkdir(parents=True)
    index_blob = fetch(INDEX_URL)
    index = lzma.decompress(index_blob).decode('utf-8')
    match = next(block for block in index.split('\n\n') if block.startswith('Package: libc6\n'))
    metadata = dict(line.split(': ', 1) for line in match.splitlines() if ': ' in line and not line.startswith(' '))
    url = 'https://deb.debian.org/debian/' + metadata['Filename']
    sha = metadata['SHA256']
    blob = fetch(url, sha)
    (DEST / Path(metadata['Filename']).name).write_bytes(blob)
    (DEST / 'official_package_metadata.txt').write_text(match, encoding='utf-8')
    lib = DEST / 'lib'
    lib.mkdir()
    links = []
    extracted = []
    with tarfile.open(fileobj=io.BytesIO(data_tar(blob)), mode='r:*') as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            normalized = str(path)
            prefix = 'lib/x86_64-linux-gnu/'
            if not normalized.startswith(prefix) or '/' in normalized[len(prefix):]:
                continue
            name = path.name
            if name in ('', '.', '..'):
                raise ValueError('unsafe member')
            target = lib / name
            if member.isfile():
                with archive.extractfile(member) as stream, target.open('xb') as output:
                    output.write(stream.read())
                target.chmod(member.mode & 0o755)
                extracted.append(name)
            elif member.issym():
                linked = PurePosixPath(member.linkname)
                if linked.is_absolute() or len(linked.parts) != 1:
                    raise ValueError('refuse non-local runtime symlink')
                links.append((target, member.linkname))
    for target, linked in links:
        if not (lib / linked).is_file():
            raise ValueError('symlink target missing')
        target.symlink_to(linked)
    loader = lib / 'ld-linux-x86-64.so.2'
    if not loader.is_file():
        raise ValueError('loader missing')
    library_path = ':'.join(map(str, [lib, ROOT / 'tools/conda_env/lib',
                                      ROOT / 'tools/runtime/blender-4.2.23-linux-x64/lib',
                                      ROOT / 'tools/runtime/lib']))
    command = [str(loader), '--library-path', library_path,
               str(ROOT / 'tools/runtime/blender-4.2.23-linux-x64/blender'), '--version']
    trial = subprocess.run(command, capture_output=True, text=True, timeout=30)
    report = {'url': url, 'sha256': sha, 'index_url': INDEX_URL,
              'index_sha256': hashlib.sha256(index_blob).hexdigest(), 'bytes': len(blob), 'files': extracted,
              'loader': str(loader), 'library_path': library_path, 'command': command,
              'rc': trial.returncode, 'stdout': trial.stdout, 'stderr': trial.stderr,
              'epoch': time.time(), 'system_libraries_modified': False,
              'conda_environment_modified': False}
    (DEST / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    raise SystemExit(0 if trial.returncode == 0 else 2)


if __name__ == '__main__':
    main()
