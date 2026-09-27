#!/usr/bin/env bash
# ===========================================================================
# Verify the new declarative PBR material hook INDEPENDENTLY, before spending
# 4 x 20 minutes on renders.
#
# The subagent created src/physim/render/materials.py and declared
#   visual.material: {pbr: dark_wood, category: wood_textures, uv_scale: 1.6}
# in assets/objects/turntable/asset.yaml.  I must confirm MYSELF, by measuring the
# rendered pixels, that:
#   * AssetSpec carries the material through (not silently dropped);
#   * the disc is no longer grey (was R/B 0.99 / sat 2.2);
#   * it matches the frozen dark_wood target (R/B ~1.99 / R/G ~1.67);
#   * it works at the REAL final render settings path, i.e. via build_scene.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== 1. does AssetSpec carry the material? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -12
import sys
sys.path.insert(0, "src")
from physim.assets import AssetManager
am = AssetManager("configs/assets.yaml", "assets")
a = am.get("turntable")
print(f"  turntable.pbr         = {getattr(a, 'pbr', '<<NO ATTRIBUTE>>')}")
print(f"  turntable.pbr_category= {getattr(a, 'pbr_category', '<<NO ATTRIBUTE>>')}")
print(f"  turntable.pbr_uv_scale= {getattr(a, 'pbr_uv_scale', '<<NO ATTRIBUTE>>')}")
# an asset WITHOUT a declared material must be unaffected
b = am.get("gso_sootheze_cold_therapy_elephant")
print(f"  elephant.pbr          = {getattr(b, 'pbr', '<<NO ATTRIBUTE>>')}  (must be None)")
PY

echo
echo "=== 2. probe render at the NEW pulled-back camera (k=1.5) ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^VR' | tail -14
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

def say(*a): print("VR", *a, flush=True)
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get("gso_sootheze_cold_therapy_elephant")
smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 8
one = SimulationResult(trajectory=res.trajectory[:1], collisions=(),
                       support_trajectory=res.support_trajectory[:1] if res.support_trajectory else None)
LOOK = [0.4140, 0.1750, 0.8084]
D = np.array([0.9340,-0.4850,1.1784]) - np.array(LOOK)
OUT = "/data/raw/huzijian/project1_database/outcomes/_tt_pbr"
os.makedirs(OUT, exist_ok=True)
for label, k in (("k1.50", 1.50), ("k1.75", 1.75)):
    cam = fixed_camera(res, {"position": (np.array(LOOK)+D*k).tolist(),
                             "look_at": LOOK, "focal_length_mm": 50.0})
    be = PhyCoBlenderBackend("third_party/phyco-sim", tempfile.mkdtemp(prefix="vr_"))
    out = be.render(smp, one, asset, ms, cam, cfg)
    img = np.asarray(out.rgb)[0].astype(np.uint8)
    Image.fromarray(img).save(os.path.join(OUT, f"PBR_{label}.png"))
    seg = np.asarray(out.segmentation)[0]
    if seg.ndim == 3: seg = seg[..., 0]
    labels = sorted(((int((seg==L).sum()), int(L)) for L in np.unique(seg) if L != 0), reverse=True)
    parts = []
    for n, L in labels[:2]:
        m = (seg == L); px = img[m].astype(np.float32)
        r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        ys,xs = np.nonzero(m)
        gray = cv2.cvtColor(px.reshape(-1,1,3).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        grain = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        parts.append(f"L{L} {100*m.mean():5.1f}% w={xs.max()-xs.min():4d} "
                     f"R/B={r/max(b,1e-6):5.2f} R/G={r/max(g,1e-6):5.2f} grain={grain:6.1f}")
    say(f"{label} dist={np.linalg.norm(D)*k:.3f}m | " + " | ".join(parts))
say("target: frozen dark_wood R/B 1.99 R/G 1.67 | grey baseline R/B 0.99")
PY
