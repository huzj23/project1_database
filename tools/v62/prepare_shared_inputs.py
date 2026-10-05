"""Copy only this task's inputs into a read-only-to-other-account snapshot.
No source permission changes, recursive chmod, deletion or overwrites.
"""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/data/raw/huzijian/project1_database')
DEST = ROOT / 'tmp/v62_shared_inputs'
assets = ['Shurtape_30_Day_Removal_UV_Delct_15', 'LEGO_Bricks_More_Creative_Suitcase',
          'Paper_Mario_Sticker_Star_Nintendo_3DS_Game', 'Hasbro_Cranium_Performance_and_Acting_Game',
          'Hasbro_Trivial_Pursuit_Family_Edition_Game']
files = [Path('models/gso') / asset / name for asset in assets
         for name in ['data.json', 'visual_geometry.obj', 'visual_geometry.mtl', 'texture.png',
                      'collision_geometry.obj', 'object.urdf']]
files += [Path('models/phyco_sim_objs/pool_table') / name
          for name in ['white_ball.obj', 'white_ball.mtl', 'white_ball.urdf']]
records = []
for relative in files:
    source = ROOT / relative
    target = DEST / relative
    if ROOT not in source.resolve().parents or ROOT not in target.resolve().parents:
        raise ValueError('input outside project')
    if target.exists():
        raise ValueError('refuse snapshot overwrite')
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as inp, target.open('xb') as out:
        shutil.copyfileobj(inp, out, 1024 * 1024)
    target.chmod(0o644)
    records.append({'source': str(source), 'snapshot': str(target), 'bytes': target.stat().st_size,
                    'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
(DEST / 'manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps({'copied': len(records), 'manifest': str(DEST / 'manifest.json')}))
