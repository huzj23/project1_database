"""Read-only resource/runtime/asset inventory. Run in project tmux + project env."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path('/data/raw/huzijian/project1_database')


def command(argv, timeout=20):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {'command': argv, 'rc': out.returncode,
                'stdout': out.stdout[:12000], 'stderr': out.stderr[:4000]}
    except Exception as exc:
        return {'command': argv, 'error': type(exc).__name__ + ': ' + str(exc)}


def main():
    label = sys.argv[1]
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'log' / 'V6.2_execution' / (label + '_probe.json')
    target = target.resolve()
    if ROOT not in target.parents:
        raise SystemExit('probe output outside workspace')
    if target.exists():
        raise SystemExit('refuse overwrite of existing probe')
    data = {'label': label, 'utc_epoch': time.time(), 'hostname': platform.node(),
            'python': sys.executable, 'version': sys.version, 'cwd': os.getcwd(),
            'cpu_count': os.cpu_count(), 'load_average': os.getloadavg(),
            'shared_workspace_stat': {'device': ROOT.stat().st_dev, 'inode': ROOT.stat().st_ino},
            'system_tools': [], 'modules': {}, 'assets': {}}
    for argv in [
        ['/usr/bin/nvidia-smi', '--query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu', '--format=csv,noheader'],
        ['/usr/bin/nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory', '--format=csv,noheader'],
        ['/usr/bin/free', '-m'],
        ['/usr/bin/tmux', '-V'],
        ['/usr/bin/getconf', 'GNU_LIBC_VERSION'],
        [str(ROOT / 'tools/runtime/blender-3.4.1-linux-x64/blender'), '--version'],
        [str(ROOT / 'tools/runtime/blender-4.2.23-linux-x64/blender'), '--version'],
    ]:
        data['system_tools'].append(command(argv))
    for name in ['numpy', 'pybullet', 'trimesh', 'PIL', 'scipy', 'bpy', 'psutil']:
        try:
            spec = importlib.util.find_spec(name)
            data['modules'][name] = None if spec is None else spec.origin
        except Exception as exc:
            data['modules'][name] = str(exc)
    names = ['Shurtape_30_Day_Removal_UV_Delct_15',
             'LEGO_Bricks_More_Creative_Suitcase',
             'Paper_Mario_Sticker_Star_Nintendo_3DS_Game']
    for name in names:
        directory = ROOT / 'models/gso' / name
        entries = []
        if directory.is_dir():
            for item in directory.rglob('*'):
                resolved = item.resolve()
                if ROOT != resolved and ROOT not in resolved.parents:
                    raise RuntimeError('asset symlink outside workspace')
                if item.is_file():
                    entries.append({'path': str(item), 'bytes': item.stat().st_size})
        data['assets'][name] = entries
    data['native_blend_exists'] = (ROOT / 'models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend').is_file()
    print(json.dumps(data, indent=2), flush=True)
    with target.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2)


if __name__ == '__main__':
    main()
