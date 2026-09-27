#!/usr/bin/env bash
# ===========================================================================
# RENDER PROBE: confirm the chosen camera really excludes the bicycle and shows
# the rolling can, using the REAL pipeline scene (same lighting, materials,
# background) at 1 frame / low spp.
#
# Class name corrected: it is `PhyCoBlenderBackend`, not `BlenderBackend`.
#
# Candidates come from the geometric pass:
#   az270_d1.4_h0.55 : bike_02 3.42 m away and OUT of frame, objfrac 0.090
#   az90_d1.4_h0.55  : bike_02 0.64 m away but out of frame (still too close)
# Render both and compare actual pixels, so the choice rests on the image rather
# than on projection maths alone.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^CB' | tail -30
import sys, os, math, tempfile
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera
from physim.render.blender_backend import PhyCoBlenderBackend

def say(*a): print("CB", *a, flush=True)

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get("gso_whey_protein_vanilla")
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)

cfg = dict(cfg)
cfg["render"] = dict(cfg["render"])
cfg["render"]["samples_per_pixel"] = 8

OUT = "/data/raw/huzijian/project1_database/outcomes/_t1b"
os.makedirs(OUT, exist_ok=True)

CANDS = [
    ("az270_d1.4", (-0.6744, -2.3931, 0.6127), (-0.6744, -0.9931, 0.1027), 40.0),
    ("az90_d1.4",  (-0.6744,  0.4069, 0.6127), (-0.6744, -0.9931, 0.1027), 40.0),
]

for label, pos, look, focal in CANDS:
    cam = fixed_camera(res, {"position": pos, "look_at": look, "focal_length_mm": focal})
    scratch = tempfile.mkdtemp(prefix=f"probe_{label}_")
    be = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    # only frame 1: keep it cheap
    from physim.physics import SimulationResult
    one = SimulationResult(trajectory=res.trajectory[:1], collisions=(),
                           support_trajectory=res.support_trajectory[:1] if res.support_trajectory else None)
    try:
        out = be.render(smp, one, asset, ms, cam, cfg)
        img = np.asarray(out.rgb)
        say(f"{label}: rendered shape={img.shape} mean={img.mean():.2f} "
            f"nonblack={(img.max(axis=2)>8).mean()*100:.1f}%")
        from PIL import Image
        p = os.path.join(OUT, f"PROBE_{label}.png")
        Image.fromarray(img.astype(np.uint8)).save(p)
        say(f"{label}: wrote {p}")
    except Exception as e:
        import traceback
        say(f"{label}: RENDER FAILED {type(e).__name__}: {str(e)[:120]}")
        traceback.print_exc()
PY
