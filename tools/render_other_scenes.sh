#!/usr/bin/env bash
# Render the other four ReplicaCAD interiors WITH their own authored lighting.
#
# Earlier attempts used a fixed external sun and they came out dark, because
# these stages have ceilings: daylight cannot reach inside, so the authored
# ceiling lights are mandatory.  This uses each stage's own lighting_config.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scenes_other"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^SC|^  '
import sys, os, json, tempfile, glob
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

def scene_cfg_for(stage):
    for c in sorted(glob.glob(os.path.join(R, "configs/scenes/*.scene_instance.json"))):
        try:
            j = json.load(open(c))
        except Exception:
            continue
        if os.path.basename(j.get("stage_instance", {}).get("template_name", "")) == stage:
            return c, j
    return None, None

def render(tag, stage, with_subject, cam_off=3.2, cam_h=1.5, spp=40):
    scratch = tempfile.mkdtemp(prefix="so_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=spp, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages", f"{stage}.glb"))
    sj, cfg = scene_cfg_for(stage)
    placed = 0
    if cfg:
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

    # Authored ceiling lights -- REQUIRED indoors (these stages have ceilings, so
    # daylight cannot reach inside).  The config to use is the one the scene
    # instance DECLARES ("default_lighting"); the v3 stages have no per-stage file
    # and all point at lighting/frl_apartment_stage.
    declared = (cfg or {}).get("default_lighting", "lighting/frl_apartment_stage")
    lcfg = os.path.join(R, "configs", declared + ".lighting_config.json")
    nlights = 0
    if os.path.isfile(lcfg):
        lj = json.load(open(lcfg))
        for _k, L in lj.get("lights", {}).items():
            if L.get("type") != "point":
                continue
            p = L["position"]
            lt = kb.PointLight(name=f"auth{nlights}",
                               position=(float(p[0]), float(-p[2]), float(p[1])),
                               intensity=float(L.get("intensity", 1.0)) * 60.0,
                               color=tuple(float(c) for c in L.get("color", [1, 1, 1])))
            scene += lt
            nlights += 1
    renderer._set_ambient_light_color((0.45, 0.45, 0.48, 1.0))
    renderer._set_background_color((0.55, 0.62, 0.75, 1.0))

    # choose a viewpoint inside the room, looking at the middle of the furniture
    lo = np.array([1e18]*3); hi = np.array([-1e18]*3)
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        nm = o.name.lower()
        if "floor" in nm or "ceiling" in nm:
            continue
        mw = np.array(o.matrix_world)
        loc = np.array([list(c) for c in o.bound_box], dtype=float)
        w = loc @ mw[:3, :3].T + mw[:3, 3]
        lo = np.minimum(lo, w.min(axis=0)); hi = np.maximum(hi, w.max(axis=0))
    c = (lo + hi) / 2.0

    if with_subject:
        meta = json.load(open(os.path.join(GSO, "data.json")))
        b = meta["kwargs"]["bounds"]; rest = -b[0][2]
        obj = kb.FileBasedObject(
            name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
            render_filename=os.path.join(GSO, "visual_geometry.obj"),
            bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
            scale=1.0, position=(float(c[0]), float(c[1]), rest), segmentation_id=2)
        scene += obj

    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = (float(c[0] + cam_off), float(c[1] - cam_off), cam_h)
    cam.look_at((float(c[0]), float(c[1]), 0.55))
    scene.camera = cam

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"SC {tag}: props={placed} lights={nlights} camera={tuple(round(v,1) for v in cam.position)}")
    print(f"  wrote {p}")

for i in range(4):
    st = f"Stage_v3_sc{i}_staging"
    render(f"sc{i}_with_subject", st, True)
PY
