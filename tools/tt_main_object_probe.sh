#!/usr/bin/env bash
# ===========================================================================
# Prove the material hook is NOT special-cased to the turntable disc.
#
# The disc camera in tt_material_probe.sh happens to put only segmentation label
# 3 in the frame, so label 2 (the actor) cannot be measured there.  Instead,
# render the SAME scene twice -- actor with no declared material, then actor with
# the material declared in memory -- and measure the pixels that CHANGED.  That
# is a real pixel measurement and it needs no segmentation label at all.
#
# Also confirms the change is scoped: the disc's pixels must be identical in both
# renders, because its own declaration is unchanged.
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
from physim.config import load_run_config
from physim.assets import AssetManager, MaterialSpec
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import fixed_camera
from physim.physics import SimulationResult
from physim.render.blender_backend import PhyCoBlenderBackend


def say(*a):
    print("AO", *a, flush=True)


am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
scen = create_scenario(cfg, asset_manager=am)
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


def render(tag, render_asset):
    scratch = tempfile.mkdtemp(prefix=f"ao_{tag}_")
    be = PhyCoBlenderBackend("third_party/phyco-sim", scratch)
    built = be.build_scene(smp, one, render_asset, ms, cam, cfg)
    layers = built.renderer.render(frames=[1], return_layers=("rgba", "segmentation"))
    img = np.asarray(layers["rgba"])[0][..., :3].astype(np.uint8)
    seg = np.asarray(layers["segmentation"])[0]
    if seg.ndim == 3:
        seg = seg[..., 0]
    Image.fromarray(img).save(os.path.join(OUT, f"ACTOR_{tag}.png"))
    return img, seg, built.diagnostics.get("declared_materials")


no_mat, seg_a, diag_a = render("no_material", asset)
with_mat, seg_b, diag_b = render(
    "with_material",
    dataclasses.replace(
        asset, material=MaterialSpec(pbr="dark_wood", category="wood_textures", uv_scale=1.6)
    ),
)
# Control: the SAME inputs rendered a second time.  Any difference here is pure
# render noise (adaptive sampling / denoising), not a material effect.
repeat, seg_c, _ = render("no_material_repeat", asset)
say("diagnostics without declaration:", diag_a)
say("diagnostics with declaration   :", diag_b)

diff = np.abs(with_mat.astype(np.int16) - no_mat.astype(np.int16)).max(axis=2)
changed = diff > 6
say(f"changed pixels: {int(changed.sum())} ({100 * changed.mean():.3f}% of frame)")
if changed.any():
    px = with_mat[changed].astype(np.float32)
    r, g, b = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
    say(
        f"ACTOR-RESULT changed region in WITH-material render: R={r:6.1f} G={g:6.1f} "
        f"B={b:6.1f} R/B={r / max(b, 1e-6):5.2f} R/G={r / max(g, 1e-6):5.2f}"
    )
else:
    say("ACTOR-RESULT: no pixel changed -> the hook did NOT reach the main object")

disc = seg_a == 3
if disc.any():
    d_cross = np.abs(
        with_mat[disc].astype(np.int16) - no_mat[disc].astype(np.int16)
    ).max()
    d_noise = np.abs(
        repeat[disc].astype(np.int16) - no_mat[disc].astype(np.int16)
    ).max()
    cross_changed = float(
        (np.abs(with_mat[disc].astype(np.int16) - no_mat[disc].astype(np.int16)).max(axis=1) > 6).mean()
    )
    noise_changed = float(
        (np.abs(repeat[disc].astype(np.int16) - no_mat[disc].astype(np.int16)).max(axis=1) > 6).mean()
    )
    say(f"disc max per-channel diff: same-input repeat = {d_noise} (render noise floor)")
    say(f"disc max per-channel diff: actor material added = {d_cross}")
    say(
        f"disc pixels moved >6: repeat={100 * noise_changed:.3f}%  "
        f"actor-material={100 * cross_changed:.3f}%"
    )
    say(
        "disc note: the disc is not re-materialed in either render; a small "
        "change is expected from global illumination (the actor sits ON the "
        "disc, so its albedo changes the light bounced onto it)."
    )

# The actor must be visibly present somewhere for this to mean anything.
say(f"segmentation labels present: {sorted(int(v) for v in np.unique(seg_b))}")
PY
