#!/usr/bin/env bash
# ===========================================================================
# Render probe, fixed, and decide the camera from ACTUAL PIXELS.
#
# Two fixes:
#  * the render worked (shape (1,1080,1920,3)) but PIL rejected it -- drop the
#    leading frame axis before saving.
#  * rather than eyeball, DIFF the two candidate images: the bicycle is a large
#    static object near the az90 camera, so it shows up as a big region that is
#    present in az90 and absent in az270.  Report where each candidate's pixels
#    come from and how much of the frame is close-range clutter.
# Also render a third candidate for comparison and print a brightness/contrast
# sanity check (a fully black or blown-out frame would be useless).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^CB' | tail -30
import sys, os, math, tempfile
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera
from physim.physics import SimulationResult
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
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 8

OUT = "/data/raw/huzijian/project1_database/outcomes/_t1b"
os.makedirs(OUT, exist_ok=True)
one = SimulationResult(trajectory=res.trajectory[:1], collisions=(),
                       support_trajectory=res.support_trajectory[:1] if res.support_trajectory else None)

CANDS = [
    ("az270_d1.4", (-0.6744, -2.3931, 0.6127), 40.0),
    ("az90_d1.4",  (-0.6744,  0.4069, 0.6127), 40.0),
    ("az270_d2.2", (-0.6744, -3.1931, 0.6127), 50.0),
]
look = (-0.6744, -0.9931, 0.1027)
imgs = {}
for label, pos, focal in CANDS:
    cam = fixed_camera(res, {"position": pos, "look_at": look, "focal_length_mm": focal})
    scratch = tempfile.mkdtemp(prefix=f"pr_{label}_")
    be = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    out = be.render(smp, one, asset, ms, cam, cfg)
    img = np.asarray(out.rgb)[0].astype(np.uint8)   # drop frame axis
    imgs[label] = img
    p = os.path.join(OUT, f"PROBE_{label}.png")
    Image.fromarray(img).save(p)
    g = img.mean(axis=2)
    say(f"{label:12s} mean={g.mean():6.2f} p05={np.percentile(g,5):6.1f} "
        f"p50={np.percentile(g,50):6.1f} p95={np.percentile(g,95):6.1f} "
        f"dark%={(g<12).mean()*100:5.1f} -> {p}")

# where does each image differ?  a near-field bicycle occupies a large contiguous
# area; report the biggest difference regions between az270 and az90
a, b = imgs["az270_d1.4"].astype(np.int16), imgs["az90_d1.4"].astype(np.int16)
d = np.abs(a-b).max(axis=2)
say(f"az270 vs az90: {100*(d>30).mean():.1f}% of pixels differ by >30")
ys, xs = np.nonzero(d > 30)
if len(ys):
    say(f"  differing bbox x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}] "
        f"centroid=({xs.mean():.0f},{ys.mean():.0f})")
    # split by halves: a bicycle "on the left" would load the left half
    say(f"  of differing px: left-half {100*(xs<960).mean():.1f}%  "
        f"right-half {100*(xs>=960).mean():.1f}%")
PY
