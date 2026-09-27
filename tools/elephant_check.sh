#!/usr/bin/env bash
# ===========================================================================
# Is the missing actor segmentation label specific to the turntable scene, or
# pre-existing across all scenes?
#
# build_scene assigns environment=1, simulated_object=2, support=3.  A turntable
# clip only ever contains {0,3}, so BOTH 1 and 2 are absent.  Check a single-body
# scene (rolling / free_fall) which has no support object: if label 2 appears there,
# the loss is specific to the two-body build; if it does not, it is pre-existing.
#
# Also answer the practical question: IS the elephant visible at all?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import glob
import numpy as np
from PIL import Image
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
for name, d in (("rolling (single body)", f"{R}/datasets/rolling/seed-001001/x1"),
                ("free_fall (single body)", f"{R}/datasets/free_fall/seed-003001/x1"),
                ("damping (single body)", f"{R}/datasets/damping/seed-007001/x1"),
                ("turntable_carry (2 bodies)", f"{R}/datasets/turntable_carry/seed-005002/x1"),
                ("turntable_spin (2 bodies)", f"{R}/datasets/turntable_spin/seed-005002/x1")):
    ss = sorted(glob.glob(d + "/segmentation/*.png"))
    if not ss:
        print(f"  {name:28s}: no segmentation"); continue
    s = np.asarray(Image.open(ss[0]))
    if s.ndim == 3: s = s[..., 0]
    print(f"  {name:28s}: labels={np.unique(s).tolist()}")
PY

echo
echo "=== IS THE ELEPHANT VISIBLE?  differential: disc-only vs disc+actor ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^EL' 
import sys, os, tempfile, dataclasses
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.physics import SimulationResult
from physim.render.blender_backend import PhyCoBlenderBackend

def say(*a): print("EL", *a, flush=True)
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_spin_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 8
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get("gso_sootheze_cold_therapy_elephant")
smp = scen.sample(seed=5002, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
say(f"elephant asset.material = {getattr(asset,'material',None)}")
say(f"sample.support_material = {getattr(smp,'support_material',None)}")
one = SimulationResult(trajectory=res.trajectory[:1], collisions=(),
                       support_trajectory=res.support_trajectory[:1])
from physim.camera import fixed_camera
cam = fixed_camera(res, dict(cfg["camera"]))
OUT = "/data/raw/huzijian/project1_database/outcomes/_tt_pbr"
os.makedirs(OUT, exist_ok=True)
def render(sample, tag):
    be = PhyCoBlenderBackend("third_party/phyco-sim", tempfile.mkdtemp(prefix="el_"))
    o = be.render(sample, one, asset, ms, cam, cfg)
    img = np.asarray(o.rgb)[0].astype(np.uint8)
    Image.fromarray(img).save(f"{OUT}/ELEPHANT_{tag}.png")
    return img, o
# with actor
img_a, o_a = render(smp, "with_actor")
# without actor: move the actor far away so it is out of frame
smp2 = dataclasses.replace(smp, initial_position=(100.0, 100.0, 100.0),
                           initial_orientation=(0,0,0,1),
                           initial_linear_velocity=(0,0,0),
                           initial_angular_velocity=(0,0,0))
one2 = SimulationResult(trajectory=[dataclasses.replace(res.trajectory[0],
                          position=(100.0,100.0,100.0))], collisions=(),
                        support_trajectory=res.support_trajectory[:1])
be = PhyCoBlenderBackend("third_party/phyco-sim", tempfile.mkdtemp(prefix="el2_"))
o_b = be.render(smp2, one2, asset, ms, cam, cfg)
img_b = np.asarray(o_b.rgb)[0].astype(np.uint8)
Image.fromarray(img_b).save(f"{OUT}/ELEPHANT_without_actor.png")
diff = (np.abs(img_a.astype(int) - img_b.astype(int)).max(axis=2) > 6)
say(f"actor-visible pixels = {diff.sum()} ({100*diff.mean():.3f}% of frame)")
if diff.sum() > 100:
    px = img_a[diff].astype(np.float32)
    r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
    ys,xs = np.nonzero(diff)
    say(f"actor pixels R={r:.1f} G={g:.1f} B={b:.1f} R/B={r/max(b,1e-6):.2f} "
        f"R/G={r/max(g,1e-6):.2f} bbox x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]")
    say("(wood would be R/B ~1.98 R/G ~1.71; grey disc is R/B 0.99)")
say(f"declared_materials = {o_a.diagnostics.get('declared_materials')}")
PY
