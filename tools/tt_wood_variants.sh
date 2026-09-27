#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Pick a wood that actually READS as mahogany (红木).
#
# The first attempt used cherry_veneer, which is a light cherry: the render came
# back reddish (R>G>B) and textured, but with R/B only 1.26 -- washed out next to
# the deep red-brown that mahogany should be (R/B roughly 1.6-2.6).
#
# So: render the same disc with four candidate treatments and MEASURE each one,
# instead of guessing which texture name looks right.
#   cherry_veneer          light reddish cherry (the baseline that was too pale)
#   american_walnut_veneer mid-dark walnut
#   dark_wood              dark neutral wood
#   dark_wood + red tint   dark wood pushed toward mahogany
#
# Output: one close-up per candidate, plus a composed sheet.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_tt_wood_variants"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PYEOF'
import sys, os, json, tempfile, math
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
import phyco_backdrops as pb
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy, cv2

def say(*a):
    print("TW", *a, flush=True)

R = os.path.join(WS, "models/backgrounds/replicad")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
DISC_R, DISC_T = 0.30, 0.022

CANDIDATES = [
    ("cherry",   "cherry_veneer",          "wood_textures", None),
    ("walnut",   "american_walnut_veneer", "wood_textures", None),
    ("dark",     "dark_wood",              "wood_textures", None),
    ("mahogany", "dark_wood",              "wood_textures", (1.55, 0.62, 0.42)),
]

scratch = tempfile.mkdtemp(prefix="twv_")
scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)

bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
for inst in cfg.get("object_instances", []):
    tpl = inst["template_name"].split("/")[-1]
    glb = os.path.join(R, "objects", f"{tpl}.glb")
    if not os.path.isfile(glb):
        continue
    before = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception:
        continue
    tr = inst.get("translation", [0, 0, 0])
    for o in [o for o in bpy.data.objects if o.name not in before]:
        if o.parent is None:
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))

lj = json.load(open(os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")))
for _k, L in lj.get("lights", {}).items():
    if L.get("type") != "point":
        continue
    p = L["position"]
    scene += kb.PointLight(name=f"auth{_k}",
                           position=(float(p[0]), float(-p[2]), float(p[1])),
                           intensity=float(L.get("intensity", 1.0)) * 60.0,
                           color=tuple(float(c) for c in L.get("color", [1, 1, 1])))
renderer._set_ambient_light_color((0.50, 0.50, 0.53, 1.0))
renderer._set_background_color((0.60, 0.68, 0.80, 1.0))
say("room + authored lights ready")

# table
TX, TY, TZ = 0.41, 0.17, 0.758
DZ = TZ + DISC_T / 2.0 + 0.002
cam = kb.PerspectiveCamera(focal_length=50.0, sensor_width=36.0)
cam.position = (TX + 0.44, TY - 0.52, TZ + 0.34)
cam.look_at((TX, TY, TZ + 0.03))
scene.camera = cam

results = []
for tag, asset, cat, tint in CANDIDATES:
    for o in list(bpy.data.objects):
        if o.name.startswith("tt_disc"):
            bpy.data.objects.remove(o, do_unlink=True)
    disc = kb.FileBasedObject(
        name=f"tt_disc_{tag}", asset_id="turntable",
        simulation_filename=os.path.join(TT, "collision/model.urdf"),
        render_filename=os.path.join(TT, "visual/model.obj"),
        scale=(1.0, 1.0, 1.0), static=False,
        position=(TX, TY, DZ), segmentation_id=3)
    disc.material = kb.PrincipledBSDFMaterial(color=(0.30, 0.12, 0.06, 1.0),
                                              roughness=0.30, metallic=0.0)
    scene += disc
    mat, info = pb.pbr_material(kb, asset, cat, uv_scale=1.6)
    ok = pb.apply_bpy_material(renderer, disc, mat)

    # optional tint: multiply the Principled base colour so the veneer reads as
    # mahogany rather than as whatever its raw albedo happens to be
    if tint is not None:
        for ob in bpy.data.objects:
            if not ob.name.startswith(f"tt_disc_{tag}"):
                continue
            for m in ob.data.materials:
                if not m or not m.use_nodes:
                    continue
                for nd in m.node_tree.nodes:
                    if nd.type == "BSDF_PRINCIPLED":
                        nd.inputs["Base Color"].default_value = (*tint, 1.0)
                        say(f"  tint applied to {m.name}")

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0][..., :3]
    cv2.imwrite(os.path.join(OUT, f"wood_{tag}.png"), img[..., ::-1])

    h, w = img.shape[:2]
    cy, cx = int(h * 0.70), int(w * 0.46)
    patch = img[cy - 40:cy + 40, cx - 90:cx + 90].astype(np.float32)
    b_, g_, r_ = patch[..., 2].mean(), patch[..., 1].mean(), patch[..., 0].mean()
    gray = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    grain = cv2.Laplacian(gray, cv2.CV_64F).var()
    results.append((tag, asset, ok, r_, g_, b_, r_ / max(b_, 1e-6), grain))
    say(f"{tag:<9} {asset:<22} tex_ok={ok} R={r_:5.1f} G={g_:5.1f} B={b_:5.1f} "
        f"R/B={r_/max(b_,1e-6):.2f} grain={grain:5.1f}")

say("")
say("target: mahogany is a deep red-brown -> R/B roughly 1.6-2.6, grain well above 5")
for tag, asset, ok, r_, g_, b_, rb, grain in results:
    verdict = "GOOD" if 1.5 <= rb <= 2.8 and grain > 5 else ("too pale" if rb < 1.5 else "check")
    say(f"  {tag:<9} R/B={rb:.2f} grain={grain:5.1f}  -> {verdict}")

# sheet
imgs = []
for tag, *_ in results:
    im = cv2.imread(os.path.join(OUT, f"wood_{tag}.png"))
    imgs.append(cv2.resize(im, (620, 349)))
sheet = np.full((30 + 2 * 349 + 20, 2 * 620, 3), 20, np.uint8)
for i, (im, (tag, asset, *_r)) in enumerate(zip(imgs, results)):
    r, c = divmod(i, 2)
    y, x = 30 + r * (349 + 10), c * 620
    sheet[y:y + 349, x:x + 620] = im
    cv2.putText(sheet, f"{tag}  ({asset})", (x + 8, y + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 220, 255), 1, cv2.LINE_AA)
cv2.imwrite(os.path.join(OUT, "WOOD_VARIANTS.png"), sheet)
say(f"wrote {OUT}/WOOD_VARIANTS.png")
PYEOF
