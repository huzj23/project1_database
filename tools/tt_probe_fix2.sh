#!/usr/bin/env bash
# ===========================================================================
# Probe the two turntable fixes with a real 1-frame pipeline render.
#
# BUG FIXED: my earlier probe called `create_scenario(cfg)` with no AssetManager,
# and the turntable scenario resolves its own support asset, so it raised
#   ValueError: ... needs an AssetManager to resolve its support asset 'turntable'
# The empty log was because I filtered stderr; the real error was never shown.
# Correct call: create_scenario(cfg, asset_manager=am).
#
# Proves from PIXELS:
#   * the disc now reads as the frozen dark_wood instead of default grey
#     (grey measured R/B 0.99; frozen dark_wood is R/B 1.83);
#   * the pull-back widens the shot (disc occupies less of the frame);
#   * the actor is still clearly visible and the disc still fits.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -25
import sys, os, tempfile
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
import cv2
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera
from physim.physics import SimulationResult
from physim.render.blender_backend import PhyCoBlenderBackend

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
scen = create_scenario(cfg, asset_manager=am)          # <-- the fix
v = variants_from_config(cfg)[0]
asset = am.get("gso_sootheze_cold_therapy_elephant")
smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
print(f"TT sample+simulate ok; support_traj={res.support_trajectory is not None}")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 8

OUT = "/data/raw/huzijian/project1_database/outcomes/_tt_fix"
os.makedirs(OUT, exist_ok=True)
one = SimulationResult(trajectory=res.trajectory[:1], collisions=(),
                       support_trajectory=res.support_trajectory[:1] if res.support_trajectory else None)
LOOK = [0.4140, 0.1750, 0.8084]
BASE = np.array([0.9340, -0.4850, 1.1784])
D = BASE - np.array(LOOK)
for label, k in (("k1.00", 1.00), ("k1.50", 1.50), ("k1.75", 1.75)):
    cam = fixed_camera(res, {"position": (np.array(LOOK) + D*k).tolist(),
                             "look_at": LOOK, "focal_length_mm": 50.0})
    scratch = tempfile.mkdtemp(prefix=f"ttf_{label}_")
    be = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    out = be.render(smp, one, asset, ms, cam, cfg)
    img = np.asarray(out.rgb)[0].astype(np.uint8)
    Image.fromarray(img).save(os.path.join(OUT, f"TTFIX_{label}.png"))
    seg = np.asarray(out.segmentation)[0]
    if seg.ndim == 3: seg = seg[..., 0]
    labels = sorted(((int((seg == L).sum()), int(L)) for L in np.unique(seg) if L != 0),
                    reverse=True)
    parts = []
    for n, L in labels[:2]:
        m = (seg == L)
        px = img[m].astype(np.float32)
        r, g, b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        ys, xs = np.nonzero(m)
        gray = cv2.cvtColor(px.reshape(-1,1,3).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        grain = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        parts.append(f"L{L} {100*m.mean():5.1f}% w={xs.max()-xs.min():4d} "
                     f"R/B={r/max(b,1e-6):4.2f} R/G={r/max(g,1e-6):4.2f} grain={grain:7.1f}")
    print(f"TT {label} dist={np.linalg.norm(D)*k:.3f}m | " + " | ".join(parts))
print("TT reference: grey R/B 0.99 grain low | frozen dark_wood R/B 1.83 R/G 1.58")
PY
