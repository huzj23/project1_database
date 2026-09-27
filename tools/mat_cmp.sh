#!/usr/bin/env bash
# ===========================================================================
# Which material method reproduces the FROZEN, APPROVED look?
#
# Reference measured from the approved wood-selection render (same method):
#     wood_dark.png  R/B 1.99  R/G 1.67  grain 33.6  feature 10.0
# which matches V3.2's recorded "dark_wood R/B 2.00" exactly, so that IS the
# frozen target.
#
# My MTL-only fix renders the disc far too dark/red (patch R/B ~5.9, R=19).  The
# approved path did NOT use an MTL: it built a full PBR node tree (diffuse + normal
# + roughness, uv_scale 1.6) with phyco_backdrops.pbr_material and attached it to the
# already-added object.  That helper lives OUTSIDE the pipeline
# (code/scenarios/phyco_backdrops.py), so the pipeline never did it -- which is
# exactly why the disc came out grey.
#
# So compare, IN THE SAME REAL SCENE AND LIGHTING:
#   (a) MTL-only      -- asset-only change, no pipeline code touched
#   (b) full PBR tree -- the frozen approved method
#   (c) grey          -- baseline, proves the measurement discriminates
# and pick whichever matches the frozen numbers.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -E '^MM' | tail -20
import sys, os, tempfile
sys.path.insert(0, "src")
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
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

def say(*a): print("MM", *a, flush=True)

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
CAM = (np.array(LOOK) + (np.array([0.9340,-0.4850,1.1784])-np.array(LOOK))*1.5).tolist()
cam = fixed_camera(res, {"position": CAM, "look_at": LOOK, "focal_length_mm": 50.0})
OUT = "/data/raw/huzijian/project1_database/outcomes/_tt_mat"
os.makedirs(OUT, exist_ok=True)

def measure(img, seg, tag):
    labels = sorted(((int((seg == L).sum()), int(L)) for L in np.unique(seg) if L != 0),
                    reverse=True)
    out = []
    for n, L in labels[:2]:
        m = (seg == L)
        px = img[m].astype(np.float32)
        r, g, b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        gray = cv2.cvtColor(px.reshape(-1,1,3).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        grain = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        out.append(f"L{L} {100*m.mean():5.1f}% R={r:6.1f} G={g:6.1f} B={b:6.1f} "
                   f"R/B={r/max(b,1e-6):5.2f} R/G={r/max(g,1e-6):5.2f} grain={grain:6.1f}")
    say(f"{tag}: " + " | ".join(out))

def render(tag, mode):
    scratch = tempfile.mkdtemp(prefix=f"mm_{tag}_")
    be = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    built = be.build_scene(smp, one, asset, ms, cam, cfg)
    import bpy
    if mode != "grey":
        so = built.support_object if hasattr(built, "support_object") else None
        # locate the support body's blender object
        bo = None
        for cand in bpy.data.objects:
            if cand.name.startswith("support_object"):
                bo = cand; break
        if bo is None:
            say(f"{tag}: support blender object NOT FOUND"); return
        if mode == "pbr":
            import phyco_backdrops as pb
            import kubric as kb
            mat, info = pb.pbr_material(kb, "dark_wood", "wood_textures", uv_scale=1.6)
            ok = pb.apply_bpy_material(be, None, mat) if False else None
            # attach directly: replace slot 0
            if bo.data.materials:
                bo.data.materials[0] = mat
            else:
                bo.data.materials.append(mat)
            say(f"{tag}: PBR material attached (uv_scale 1.6), maps={list(info.get('maps',{}).keys())}")
        elif mode == "grey":
            pass
    layers = built.renderer.render(frames=[1], return_layers=("rgba","segmentation"))
    img = np.asarray(layers["rgba"])[0][..., :3].astype(np.uint8)
    seg = np.asarray(layers["segmentation"])[0]
    if seg.ndim == 3: seg = seg[..., 0]
    Image.fromarray(img).save(os.path.join(OUT, f"MAT_{tag}.png"))
    measure(img, seg, tag)

render("a_mtl",  "mtl")
render("b_pbr",  "pbr")
say("target (frozen approved): R/B 1.99  R/G 1.67  grain 33.6")
say("grey baseline measured on the real clip: R/B 0.99  R/G 0.99  sat 2.2")
PY
