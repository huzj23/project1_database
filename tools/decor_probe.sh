#!/usr/bin/env bash
# Can we make the apartment look lived-in rather than showroom-clean?
#
# Four levers, rendered as a comparison so the effect of each is visible:
#   A  baseline      : our synthetic sun+fill, original materials   (what we shipped)
#   B  authored light: the apartment's own ceiling point lights from lighting_config
#   C  B + wall swap : plaster wall PBR replaces the flat white walls
#   D  C + clutter   : extra everyday props scattered on surfaces
#
# The stage meshes are individually named (frl_apartment_floor, ..._wall, ...), so
# materials are addressable per surface.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_decor_probe"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^DEC|^  '
import sys, os, json, tempfile, random
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

R = os.path.join(WS, "models/backgrounds/replicad")
STAGE = os.path.join(R, "stages/frl_apartment_stage.glb")
SJ = os.path.join(R, "configs/scenes/apt_0.scene_instance.json")
LIGHT_CFG = os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")

def load_world(renderer, scene, clutter):
    bpy.ops.import_scene.gltf(filepath=STAGE)
    cfg = json.load(open(SJ))
    placed = []
    for inst in cfg.get("object_instances", []):
        tpl = inst["template_name"].split("/")[-1]
        glb = os.path.join(R, "objects", f"{tpl}.glb")
        if not os.path.isfile(glb):
            continue
        b2 = {o.name for o in bpy.data.objects}
        try:
            bpy.ops.import_scene.gltf(filepath=glb)
        except Exception:
            continue
        tr = inst.get("translation", [0, 0, 0])
        for o in [o for o in bpy.data.objects if o.name not in b2]:
            if o.parent is None:
                o.location = (o.location.x + float(tr[0]),
                              o.location.y - float(tr[2]),
                              o.location.z + float(tr[1]))
        placed.append(tpl)
    if clutter:
        # a few small everyday items dropped near the furniture cluster
        extra = ["cup_01", "book_03", "bowl_02", "shoe_02", "remote-control_01",
                 "plate_01", "towel", "sponge_dish"]
        random.seed(7)
        for e in extra:
            glb = os.path.join(R, "objects", f"frl_apartment_{e}.glb")
            if not os.path.isfile(glb):
                continue
            b2 = {o.name for o in bpy.data.objects}
            try:
                bpy.ops.import_scene.gltf(filepath=glb)
            except Exception:
                continue
            for o in [o for o in bpy.data.objects if o.name not in b2]:
                if o.parent is None:
                    o.location = (o.location.x + random.uniform(-1.2, 2.2),
                                  o.location.y + random.uniform(-2.4, 0.4),
                                  o.location.z + 0.45)
            placed.append(e)
    return placed

def apply_wall_swap(renderer):
    """Replace the flat white wall/ceiling material with a plaster PBR."""
    try:
        mat, info = pb.pbr_material(kb, "painted_plaster_wall", "ground_textures",
                                    uv_scale=3.0)
    except Exception as e:
        print(f"  wall material build failed: {e}")
        return 0
    n = 0
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        nm = o.name.lower()
        if "wall" not in nm and "ceiling" not in nm:
            continue
        if not o.data.materials:
            continue
        o.data.materials[0] = mat
        n += 1
    return n

def add_authored_lights(scene, scale=60.0):
    cfg = json.load(open(LIGHT_CFG))
    n = 0
    for _k, L in cfg.get("lights", {}).items():
        if L.get("type") != "point":
            continue
        p = L["position"]           # habitat Y-up -> blender Z-up
        pos = (float(p[0]), float(-p[2]), float(p[1]))
        lt = kb.PointLight(name=f"auth{n}", position=pos,
                           intensity=float(L.get("intensity", 1.0)) * scale,
                           color=tuple(float(c) for c in L.get("color", [1, 1, 1])))
        scene += lt
        n += 1
    return n

def render(tag, use_authored, wall_swap, clutter, cam_pos, aim):
    scratch = tempfile.mkdtemp(prefix="dec_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=40, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)
    props = load_world(renderer, scene, clutter)

    renderer._set_ambient_light_color((0.55, 0.55, 0.58, 1.0))
    renderer._set_background_color((0.62, 0.70, 0.82, 1.0))
    nl = 0
    if use_authored:
        nl = add_authored_lights(scene)
        # a weak sun only, so the ceiling lights dominate the mood
        sun = kb.DirectionalLight(name="sun", position=(4, -5, 7), intensity=0.8)
        sun.look_at((1.0, -1.7, 0.5)); scene += sun
    else:
        sun = kb.DirectionalLight(name="sun", position=(4, -5, 7), intensity=3.0)
        sun.look_at((1.0, -1.7, 0.4)); scene += sun
        fill = kb.RectAreaLight(name="fill", position=(-1.7, -0.2, 2.4),
                                intensity=340.0, width=5.0, height=3.0)
        fill.look_at((1.0, -1.7, 0.5)); scene += fill

    nw = apply_wall_swap(renderer) if wall_swap else 0
    print(f"DEC {tag}: props={len(props)} authored_lights={nl} walls_swapped={nw} clutter={clutter}")

    cam = kb.PerspectiveCamera(focal_length=32.0, sensor_width=36.0)
    cam.position = cam_pos
    cam.look_at(aim)
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"  wrote {p}")

CAM = (2.6, -3.4, 1.55)
AIM = (1.2, -1.7, 0.55)
render("A_baseline",  False, False, False, CAM, AIM)
render("B_authored",  True,  False, False, CAM, AIM)
render("C_wall_swap", True,  True,  False, CAM, AIM)
render("D_clutter",   True,  True,  True,  CAM, AIM)
PY
