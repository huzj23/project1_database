#!/usr/bin/env bash
# The probe log is EMPTY (0 bytes) and the tmux session vanished, so the script is
# dying before it can even print.  `set -e` is NOT set, but the very first thing the
# heredoc does is import the pipeline; if `python -u` writes nothing at all, the
# process is likely being killed or the heredoc never ran.
#
# Run the SAME python body directly in the foreground with NO pipe and NO filter,
# so any traceback is visible.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "--- python version / interpreter ---"
"$WS/tools/conda_env/bin/python" -c "import sys; print(sys.version)"

echo "--- step 1: imports ---"
"$WS/tools/conda_env/bin/python" -u -c "
import sys
sys.path.insert(0, 'src')
import numpy
print('numpy', numpy.__version__)
from physim.config import load_run_config
print('config ok')
from physim.assets import AssetManager
from physim.maps import MapManager
print('assets/maps ok')
from physim.scenarios import create_scenario, variants_from_config
print('scenarios ok')
from physim.physics.pybullet_backend import PyBulletBackend
print('physics ok')
from physim.camera import fixed_camera
print('camera ok')
from physim.render.blender_backend import PhyCoBlenderBackend
print('render ok')
" 2>&1 | tail -20

echo
echo "--- step 2: simulation only (no render) ---"
"$WS/tools/conda_env/bin/python" -u -c "
import sys; sys.path.insert(0, 'src')
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
am = AssetManager('configs/assets.yaml','assets')
mm = MapManager('configs/maps.yaml', am)
ms = mm.get('replicad_apartment', require_files=True)
cfg = load_run_config('configs/server.yaml', scenario='turntable_carry_gso')
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get('gso_sootheze_cold_therapy_elephant')
smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
print('  sample ok')
res = PyBulletBackend('third_party/phyco-sim').simulate(smp, ms, asset)
print('  simulate ok, support_trajectory=', res.support_trajectory is not None)
print('  support_visual_path=', smp.support_visual_path)
" 2>&1 | tail -20
