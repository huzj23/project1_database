#!/usr/bin/env bash
# Answer three questions at once:
#   (a) does the imported stage GLB carry ANY lights of its own?  (double-light risk)
#   (b) what does the object-in-scene proportion look like, and where should the
#       camera sit?
#   (c) interior views of the OTHER four stages, which the outside shots could not
#       show because they have ceilings.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scene_interior2"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^Q|^  '
import sys, os, json, tempfile
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy, cv2

R = os.path.join(WS, "models/backgrounds/replicad")
GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")

# ---------- (a) lights inside the stage GLB ----------
print("Q (a) lights inside the imported stage GLB")
tmp = tempfile.mkdtemp(prefix="chk_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, tmp, samples_per_pixel=1, use_denoising=False, verbose=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
glb_lights = [o.name for o in bpy.data.objects if o.type == "LIGHT"]
print(f"  stage GLB light objects : {len(glb_lights)}  {glb_lights}")
print(f"  => the GLB carries NO lights; Habitat keeps them in lighting_config.json")
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for m in list(bpy.data.meshes):
    bpy.data.meshes.remove(m)

# ---------- (b) object in scene: proportion + camera ----------
def load_room(clutter=True):
    bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages/frl_apartment_stage.glb"))
    cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
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

def authored_lights(scene, scale=60.0):
    cfg = json.load(open(os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")))
    n = 0
    for _k, L in cfg.get("lights", {}).items():
        if L.get("type") != "point":
            continue
        p = L["position"]
        lt = kb.PointLight(name=f"auth{n}", position=(float(p[0]), float(-p[2]), float(p[1])),
                           intensity=float(L.get("intensity", 1.0)) * scale,
                           color=tuple(float(c) for c in L.get("color", [1, 1, 1])))
        scene += lt
        n += 1
    return n

def render_obj(tag, obj_xy, cam_off, cam_h, aim_h, res=(1280, 720)):
    scratch = tempfile.mkdtemp(prefix="ob_")
    scene = kb.Scene(resolution=res, frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=40, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)
    load_room()
    n = authored_lights(scene)
    renderer._set_ambient_light_color((0.42, 0.42, 0.45, 1.0))
    renderer._set_background_color((0.60, 0.70, 0.85, 1.0))

    # GSO actor, resting on the floor (floor_z ~ 0 after the direct import)
    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    span = [b[1][i] - b[0][i] for i in range(3)]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(obj_xy[0], obj_xy[1], rest), segmentation_id=2)
    scene += obj

    cam = kb.PerspectiveCamera(focal_length=50.0, sensor_width=36.0)
    cam.position = (obj_xy[0] + cam_off[0], obj_xy[1] + cam_off[1], cam_h)
    cam.look_at((obj_xy[0], obj_xy[1], aim_h))
    scene.camera = cam

    d = float(np.hypot(cam_off[0], cam_off[1]))
    vis_w = 2 * d * np.tan(np.arctan(36 / (2 * 50.0)))
    print(f"Q {tag}: obj at {obj_xy} size={np.round(span,3).tolist()}m  "
          f"cam_d={d:.2f}m lights={n}  object = {100*span[0]/vis_w:.0f}% of frame width")

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"  wrote {p}")

# an open patch of floor, viewed from a couple of stand-offs
render_obj("B1_floor_close",  (1.30, -3.20), (0.90, -1.20), 1.05, 0.28)
render_obj("B2_floor_medium", (1.30, -3.20), (1.60, -2.10), 1.25, 0.25)

# ---------- (c) interior views of the other four stages ----------
def render_stage_interior(tag, stage, scene_json, cam_pos, aim):
    scratch = tempfile.mkdtemp(prefix="st_")
    scene = kb.Scene(resolution=(960, 540), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=28, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)
    bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages", stage))
    placed = 0
    if scene_json and os.path.isfile(scene_json):
        cfg = json.load(open(scene_json))
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
            placed += 1
    renderer._set_ambient_light_color((0.72, 0.72, 0.75, 1.0))
    renderer._set_background_color((0.62, 0.70, 0.82, 1.0))
    sun = kb.DirectionalLight(name="sun", position=(3, -4, 6), intensity=2.6)
    sun.look_at(aim); scene += sun
    fill = kb.RectAreaLight(name="fill", position=(-2, 2, 2.4), intensity=300.0,
                            width=5.0, height=3.0)
    fill.look_at(aim); scene += fill
    cam = kb.PerspectiveCamera(focal_length=30.0, sensor_width=36.0)
    cam.position = cam_pos; cam.look_at(aim)
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgb1" if False else "rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"Q {tag}: props={placed}")
    print(f"  wrote {p}")

for i in range(4):
    st = f"Stage_v3_sc{i}_staging"
    js = os.path.join(R, f"configs/scenes/v3_sc{i}_staging_00.scene_instance.json")
    render_stage_interior(f"C{i}_sc{i}_interior", f"{st}.glb", js,
                          (2.2, -3.4, 1.55), (0.8, -0.6, 0.55))
PY
