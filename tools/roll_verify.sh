#!/usr/bin/env bash
# ===========================================================================
# 1. Is the whey can GENUINELY rolling (not sliding)?
#    For rolling without slipping: |omega_horizontal| * r == |v|, i.e. slip = 1.
#    A sliding body has omega ~ 0 while v != 0.
# 2. Backward compat: do all 14 original clips still pass (physics + camera)?
# 3. Where is the BICYCLE the user dislikes?  Find it in the scene blend so the
#    new camera can be aimed to exclude it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== 1. rolling physics: slip = |omega|*r / |v| ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import sys, math
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get("gso_whey_protein_vanilla")
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])

p = np.array([s.position for s in res.trajectory])
vlin = np.array([s.linear_velocity for s in res.trajectory])
omg = np.array([s.angular_velocity for s in res.trajectory])
r = smp.support_height
print(f"  initial_quaternion = {tuple(round(x,4) for x in smp.initial_quaternion)}")
print(f"  support_height r   = {r:.5f}  (upright would be 0.08232; cross-section 0.06097)")
print(f"  valid={rep.valid} reasons={list(rep.reasons)}")
print(f"  z = {p[:,2].min():.5f}..{p[:,2].max():.5f}  (flat => resting, not tumbling)")
print(f"  speed |v| = {np.linalg.norm(vlin[:,:2],axis=1).min():.4f}.."
      f"{np.linalg.norm(vlin[:,:2],axis=1).max():.4f} m/s")
print(f"  |omega| = {np.linalg.norm(omg,axis=1).min():.4f}.."
      f"{np.linalg.norm(omg,axis=1).max():.4f} rad/s")
sp = np.linalg.norm(vlin[:,:2],axis=1)
om = np.linalg.norm(omg,axis=1)
slip = np.where(sp > 1e-6, om*r/np.maximum(sp,1e-9), np.nan)
print(f"  slip = |omega|*r/|v| = {np.nanmin(slip):.4f}..{np.nanmax(slip):.4f}  "
      f"(1.0 = perfect rolling, ~0 = pure sliding)")
print(f"  omega direction (frame 0): {np.round(omg[0],4).tolist()}")
print(f"  v direction (frame 0)    : {np.round(vlin[0],4).tolist()}")
print(f"  => spin axis is {'HORIZONTAL (rolling)' if abs(omg[:,2].mean()) < 0.2*np.abs(omg).mean() else 'VERTICAL (spinning)'}")
PY

echo
echo "=== 2. backward compat: 14 original clips ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -3

echo
echo "=== 3. locate the bicycle in the scene blend ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -viE 'tensorflow|oneDNN|TF_ENABLE|AVX|Warning' | tail -30
import bpy
p = "assets/environments/replicad_apartment/visual/scene.blend"
bpy.ops.wm.open_mainfile(filepath=p)
names = sorted(o.name for o in bpy.data.objects)
print(f"  total objects: {len(names)}")
hits = [n for n in names if any(k in n.lower() for k in
        ("bike","bicycle","cycle","velo","wheel","seat","frame_"))]
print(f"  bicycle-ish names: {hits[:20]}")
print("  sample of all names:")
for n in names[:40]:
    print("   ", n)
PY
