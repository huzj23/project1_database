#!/usr/bin/env bash
# ===========================================================================
# Measure the turntable disc's pixels in a REAL pipeline render.
#
# This probe does NOT attach anything by hand: it calls build_scene() and then
# measures whatever material the pipeline produced.  Run it before and after the
# declarative-material change to get the before/after numbers from one harness.
#
#   grey (bug)          : disc R/B ~0.99  R/G ~0.99
#   frozen dark_wood    : disc R/B ~1.99  R/G ~1.67
#
# No stderr filtering: a previous probe in this project hid a real traceback
# behind `grep -E '^MM'`, which wasted a lot of time.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys, os, tempfile, dataclasses
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
import cv2
from physim.config import load_run_config
from physim.assets import AssetManager
try:                       # absent before the declarative-material change
    from physim.assets import MaterialSpec
except ImportError:
    MaterialSpec = None
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera
from physim.physics import SimulationResult
from physim.render.blender_backend import PhyCoBlenderBackend


def say(*a):
    print("MM", *a, flush=True)


am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
scen = create_scenario(cfg, asset_manager=am)          # needs the AssetManager
v = variants_from_config(cfg)[0]
asset = am.get("gso_sootheze_cold_therapy_elephant")
smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
cfg = dict(cfg)
cfg["render"] = dict(cfg["render"])
cfg["render"]["samples_per_pixel"] = 8

one = SimulationResult(
    trajectory=res.trajectory[:1],
    collisions=(),
    support_trajectory=res.support_trajectory[:1] if res.support_trajectory else None,
)
LOOK = [0.4140, 0.1750, 0.8084]
CAM = (np.array(LOOK) + (np.array([0.9340, -0.4850, 1.1784]) - np.array(LOOK)) * 1.5).tolist()
cam = fixed_camera(res, {"position": CAM, "look_at": LOOK, "focal_length_mm": 50.0})

OUT = "/data/raw/huzijian/project1_database/outcomes/_tt_mat"
os.makedirs(OUT, exist_ok=True)

say("manifest turntable.material  =", getattr(am.get("turntable"), "material", "<field absent>"))
say("sample.support_material      =", getattr(smp, "support_material", "<field absent>"))
say("main asset.material          =", getattr(asset, "material", "<field absent>"))


def measure(img, seg, tag, want_label=3):
    """Report the pixels of ``want_label`` (3 = the turntable disc).

    The actor (label 2) is small and partly occluded here, so measuring "the
    second-biggest label" would silently report the disc twice.
    """
    labels = sorted(
        ((int((seg == L).sum()), int(L)) for L in np.unique(seg) if L != 0),
        reverse=True,
    )
    parts = []
    for n, L in labels[:3]:
        m = (seg == L)
        px = img[m].astype(np.float32)
        r, g, b = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
        gray = cv2.cvtColor(px.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        grain = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sat = float((px.max(axis=1) - px.min(axis=1)).mean())
        marker = " <== TARGET" if L == want_label else ""
        parts.append(
            f"L{L} {100 * m.mean():5.1f}% R={r:6.1f} G={g:6.1f} B={b:6.1f} "
            f"R/B={r / max(b, 1e-6):5.2f} R/G={r / max(g, 1e-6):5.2f} "
            f"grain={grain:6.1f} sat={sat:5.1f}{marker}"
        )
    say(f"RESULT {tag}: " + " | ".join(parts))


def render_and_measure(tag, render_asset=None, render_sample=None):
    scratch = tempfile.mkdtemp(prefix=f"mprobe_{tag}_")
    be = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    built = be.build_scene(
        render_sample if render_sample is not None else smp,
        one,
        render_asset if render_asset is not None else asset,
        ms,
        cam,
        cfg,
    )
    import bpy
    for o in sorted(bpy.data.objects, key=lambda o: o.name):
        if o.type != "MESH":
            continue
        mats = [m.name if m is not None else None for m in o.data.materials]
        say(f"MM object {o.name!r}: materials={mats} uv_layers={len(o.data.uv_layers)}")
    diag = built.diagnostics.get("declared_materials")
    say(f"MM diagnostics declared_materials = {diag}")
    layers = built.renderer.render(frames=[1], return_layers=("rgba", "segmentation"))
    img = np.asarray(layers["rgba"])[0][..., :3].astype(np.uint8)
    seg = np.asarray(layers["segmentation"])[0]
    if seg.ndim == 3:
        seg = seg[..., 0]
    Image.fromarray(img).save(os.path.join(OUT, f"MPROBE_{tag}.png"))
    measure(img, seg, tag)
    return img, seg


render_and_measure("disc")

# Same mechanism, main simulated object: give the actor the same declared
# material in memory (no manifest is touched) and prove the actor's own pixels
# change too -- i.e. the hook is not special-cased to the disc.
if MaterialSpec is not None:
    img2, seg2 = render_and_measure(
        "main_object",
        render_asset=dataclasses.replace(
            asset,
            material=MaterialSpec(pbr="dark_wood", category="wood_textures", uv_scale=1.6),
        ),
    )
    # Label 2 is the actor itself; prove the same hook changed ITS pixels rather
    # than reporting the disc again.
    actor = (seg2 == 2)
    if actor.any():
        px = img2[actor].astype(np.float32)
        r, g, b = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
        say(
            f"RESULT actor_L2 {100 * actor.mean():5.1f}% R={r:6.1f} G={g:6.1f} "
            f"B={b:6.1f} R/B={r / max(b, 1e-6):5.2f} R/G={r / max(g, 1e-6):5.2f}"
        )
    else:
        say("RESULT actor_L2: label 2 not visible in this frame")
else:
    say("SKIP main_object probe: AssetSpec has no 'material' field yet")

say("reference: grey disc R/B 0.99 R/G 0.99 sat 2.2 | frozen dark_wood R/B 1.99 R/G 1.67")
if MaterialSpec is None:
    say("NOTE: MaterialSpec absent -> this run measured the PRE-CHANGE baseline")
PY
