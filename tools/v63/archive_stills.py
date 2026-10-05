"""Freeze complete reviewed-run inputs and PNGs to a new outcomes directory."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path('/data/raw/huzijian/project1_database')
OUT = ROOT / 'outcomes/v63/radio_scurve_domino/20261006_static_review'
OUT.mkdir(parents=True, exist_ok=False)
SCENE = ROOT / 'tmp/v63_node11/static_scene_r5'
composition = json.loads((SCENE / 'composition_report.json').read_text())
rows = []
for spec in composition['cameras']:
    ident = spec['id']
    batch = 'r3' if ident == '10b_follow_camera_side' else ('r2' if ident == '04_drop_bridge' else 'r1')
    source = ROOT / ('tmp/v63_node12/static_gpu_' + batch)
    record_path = source / (ident + '_render.json')
    record = json.loads(record_path.read_text())
    if record['devices'].get('observed_contexts') != ['GPU-665e9626-9862-7424-fc4a-dc90d61079fa']:
        raise RuntimeError('device proof missing')
    if record['devices'].get('other_pids'):
        raise RuntimeError('shared GPU rejected')
    for filename in (ident + '.png', ident + '_render.json'):
        target = OUT / filename
        if target.exists():
            raise RuntimeError('refuse overwrite')
        shutil.copyfile(source / filename, target)
    image = OUT / (ident + '.png')
    rows.append({'id': ident, 'source': str(source / image.name), 'file': str(image),
                 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(), 'bytes': image.stat().st_size,
                 'render_seconds': record['seconds'], 'camera': spec})
for src, name in [(SCENE / 'composition_report.json', 'composition_report.json'),
                  (ROOT / 'tmp/v63_node11/relay_probe_r2/summary.json', 'local_relay_diagnostics.json'),
                  (ROOT / 'tmp/v63_node11/common_assets_r1/manifest.json', 'common_assets_manifest.json'),
                  (ROOT / 'tmp/v63_node12/gpu_scope_probe_r2/verified_device.json', 'verified_gpu_device.json')]:
    shutil.copyfile(src, OUT / name)
with (OUT / 'DELIVERY_MANIFEST.json').open('x') as handle:
    json.dump({'status': 'STATIC_REVIEW_ONLY_PENDING_USER_AND_PHYSICS', 'images': rows,
               'ground_count': composition['ground_count'], 'all_actor_count': composition['all_actor_count'],
               'route_length_m': composition['route_length_m'], 'source_sha256': composition['source_sha256'],
               'physics_not_accepted': True, 'retired_files_deleted': False,
               'scene_input': str(SCENE / 'review_scene.blend'),
               'final_scene': str(OUT / 'review_scene.blend')}, handle, indent=2)
print('ARCHIVE_COMPLETE', str(OUT), len(rows), flush=True)
