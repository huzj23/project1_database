"""Archive only this task's named outputs. Copy, hash, never delete/overwrite."""
from pathlib import Path
import hashlib
import json
import shutil
import time

ROOT = Path('/data/raw/huzijian/project1_database').resolve()
SOURCE = ROOT / 'tmp/v62_node12/run_20261005_pilot4'
DEST = ROOT / 'outcomes/v62/radio_mixed_domino/20261005_pilot4'
assert ROOT in SOURCE.resolve().parents and ROOT in DEST.resolve().parents
report = json.loads((SOURCE/'pilot_report.json').read_text())
if len(report['render_results']) != 4 or not report.get('author_lights_unchanged') or report.get('author_objects_transform_changes'):
    raise SystemExit('incomplete pilot or author-scene guard failed')
files = ['01_table_story.png','02_table_side.png','03_drop_bridge.png','05_tape_and_suitcase.png',
         'pilot_report.json','pilot.blend']
for name in files:
    assert (SOURCE/name).is_file()
DEST.mkdir(parents=True, exist_ok=False)
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):
            h.update(block)
    return h.hexdigest()
manifest = {'status':'VISUAL_PILOT_NOT_FULL_STAGE1_ACCEPTANCE','epoch':time.time(),'files':[],
            'raw_output':str(SOURCE),'archive':str(DEST)}
for name in files:
    a,b = SOURCE/name, DEST/name
    shutil.copy2(a,b)
    ha,hb=sha(a),sha(b)
    if ha!=hb:
        raise RuntimeError('copy hash mismatch: '+name)
    manifest['files'].append({'name':name,'bytes':b.stat().st_size,'sha256':hb})
original = ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend'
manifest['original_scene_sha256'] = sha(original)
manifest['original_scene_expected_sha256'] = 'be1247889cee3ce10028ee1ef1066a96728b3c2aa191ad12b51cc3b578fa4ae9'
manifest['source_hash_matches_baseline'] = manifest['original_scene_sha256']==manifest['original_scene_expected_sha256']
manifest['renderer_sha256'] = sha(ROOT/'tools/v62/pilot_render_r4.py')
manifest['note'] = 'Working blend retained server-side; only stills and small reports need local download. No source or failed files removed.'
(DEST/'artifact_manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2),flush=True)
