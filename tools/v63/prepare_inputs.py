"""Recover the registered Poly Haven baseball and task-scoped readable inputs.

Server only, CPU/network work. Never changes originals, deletes, or overwrites.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request

ROOT = Path('/data/raw/huzijian/project1_database')
DEST = ROOT / 'tmp/v63_shared_inputs'
BALL = ROOT / 'models/asset_recovery/v63/sphere_baseball/20261006_original4k'
ASSETS = [
    'Paper_Mario_Sticker_Star_Nintendo_3DS_Game',
    'New_Super_Mario_BrosWii_Wii_Game',
    'House_of_Cards_The_Complete_First_Season_4_Discs_DVD',
    'Hasbro_Cranium_Performance_and_Acting_Game',
    'Hasbro_Trivial_Pursuit_Family_Edition_Game',
    'Supernatural_Ouija_Board_Game',
    'Shurtape_30_Day_Removal_UV_Delct_15',
]


def checked(path):
    path = path.resolve()
    if ROOT not in path.parents:
        raise ValueError('outside project: ' + str(path))
    return path


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def exclusive_json(path, data):
    checked(path).parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as handle:
        json.dump(data, handle, indent=2)
    path.chmod(0o644)


def request(url):
    if not url.startswith(('https://api.polyhaven.com/', 'https://dl.polyhaven.org/')):
        raise ValueError('unexpected asset host')
    req = urllib.request.Request(url, headers={'User-Agent': 'Project1-asset-recovery/6.3'})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def main():
    os.umask(0o022)
    DEST.mkdir(parents=True, exist_ok=False)
    BALL.mkdir(parents=True, exist_ok=False)
    api = json.loads(request('https://api.polyhaven.com/files/baseball_01'))
    exclusive_json(BALL / 'official_files_index.json', api)
    spec = api['gltf']['4k']['gltf']
    files = {'baseball_01_4k.gltf': spec, **spec['include']}
    report = {'epoch': time.time(), 'source': 'https://polyhaven.com/a/baseball_01',
              'author': 'Rico Cilliers', 'license': 'CC0-1.0',
              'ball_source': str(BALL), 'ball_files': [], 'gso_files': []}
    for relative, meta in files.items():
        path = checked(BALL / relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = request(meta['url'])
        if len(blob) != meta['size'] or hashlib.md5(blob).hexdigest() != meta['md5']:
            raise RuntimeError('official size/md5 mismatch: ' + relative)
        with path.open('xb') as handle:
            handle.write(blob)
        path.chmod(0o644)
        report['ball_files'].append({'file': str(path), 'bytes': len(blob),
                                    'url': meta['url'], 'sha256': digest(path)})
        print('RECOVERED', relative, len(blob), flush=True)
    for asset in ASSETS:
        for filename in ['data.json', 'visual_geometry.obj', 'visual_geometry.mtl',
                         'texture.png', 'collision_geometry.obj', 'object.urdf']:
            source = checked(ROOT / 'models/gso' / asset / filename)
            target = checked(DEST / 'models/gso' / asset / filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open('rb') as inp, target.open('xb') as out:
                shutil.copyfileobj(inp, out, 1024 * 1024)
            target.chmod(0o644)
            report['gso_files'].append({'source': str(source), 'snapshot': str(target),
                                      'bytes': target.stat().st_size, 'sha256': digest(target)})
        print('COPIED', asset, flush=True)
    exclusive_json(DEST / 'manifest.json', report)
    print('PREPARE_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
