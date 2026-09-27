#!/usr/bin/env bash
# Re-shoot the four rooms with the camera aimed at the FURNITURE, not by hand.
#
# The hard-coded viewpoints worked for one room and failed for others: some ended
# up facing a blank wall or clipping a door frame.  Instead, compute the furniture
# cluster's bounding box per scene and orbit the camera around its centre at a
# fixed stand-off, clamped inside the room shell.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scenes_multi2"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^MV2|^  '
import sys, os, json, tempfile, glob, math
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
from mathutils import Vector

R = os.path.join(WS, "models/backgrounds/replicad")
STAGES = ["Stage_v3_sc0_staging", "Stage_v3_sc1_staging",
          "Stage_v3_sc2_staging", "Stage_v3_sc3_staging"]
ROOM = dict(x=(-2.55, 4.45), y=(-7.95, 4.75))

def cfg_for(stage):
    for c in sorted(glob.glob(os.path.join(R, "configs/scenes/*.scene_instance.json"))):
        try:
            j = json.load(open(c))
        except Exception:
            continue
        if os.path.basename(j.get("stage_instance", {}).get("template_name", "")) == stage:
            return c, j
    return None, None

def build(stage):
    scratch = tempfile.mkdtemp(prefix="mv2_")
    scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)
    bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages", f"{stage}.glb"))
    sj, cfg = cfg_for(stage)
    props = []
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
            new = [o for o in bpy.data.objects if o.name not in b2]
            for o in new:
                if o.parent is None:
                    o.location = (o.location.x + float(tr[0]),
                                  o.location.y - float(tr[2]),
                                  o.location.z + float(tr[1]))
            props.extend(new)
    declared = (cfg or {}).get("default_lighting", "lighting/frl_apartment_stage")
    lcfg = os.path.join(R, "configs", declared + ".lighting_config.json")
    n = 0
    if os.path.isfile(lcfg):
        lj = json.load(open(lcfg))
        for _k, L in lj.get("lights", {}).items():
            if L.get("type") != "point":
                continue
            p = L["position"]
            scene += kb.PointLight(name=f"auth{n}",
                                   position=(float(p[0]), float(-p[2]), float(p[1])),
                                   intensity=float(L.get("intensity", 1.0)) * 60.0,
                                   color=tuple(float(c) for c in L.get("color", [1, 1, 1])))
            n += 1
    renderer._set_ambient_light_color((0.50, 0.50, 0.53, 1.0))
    renderer._set_background_color((0.60, 0.68, 0.80, 1.0))

    # furniture cluster bounds -- ignore floor/ceiling shells
    lo = np.array([1e18]*3); hi = np.array([-1e18]*3)
    for o in props:
        if o.type != "MESH":
            continue
        mw = np.array(o.matrix_world)
        loc = np.array([list(c) for c in o.bound_box], dtype=float)
        w = loc @ mw[:3, :3].T + mw[:3, 3]
        if w[:, 2].max() < 0.06:      # flat decals / rugs
            continue
        lo = np.minimum(lo, w.min(axis=0)); hi = np.maximum(hi, w.max(axis=0))
    c = (lo + hi) / 2.0
    return scene, renderer, props, n, c, lo, hi

def render_view(scene, renderer, tag, pos, aim, focal, path):
    cam = kb.PerspectiveCamera(focal_length=focal, sensor_width=36.0)
    cam.position = pos
    cam.look_at(aim)
    scene.camera = cam
    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    cv2.imwrite(path, img[..., :3][..., ::-1])

# viewpoints around the furniture centre: two low, one higher
ANGLES = [("a", 35.0, 1.45, 30.0), ("b", 145.0, 1.45, 28.0), ("c", 255.0, 2.05, 26.0)]
DIST = 3.0

for si, stage in enumerate(STAGES):
    tg = stage.replace("_staging", "")
    scene, renderer, props, n, c, lo, hi = build(stage)
    print(f"MV2 {tg}: props={len(props)} lights={n} "
          f"centre=({c[0]:.2f},{c[1]:.2f}) span={np.round(hi-lo,1).tolist()}")
    for name, az, h, focal in ANGLES:
        a = math.radians(az)
        pos = (float(np.clip(c[0] + DIST * math.cos(a), ROOM['x'][0], ROOM['x'][1])),
               float(np.clip(c[1] + DIST * math.sin(a), ROOM['y'][0], ROOM['y'][1])),
               h)
        p = os.path.join(OUT, f"{si}_{tg}_{name}.png")
        render_view(scene, renderer, tg, pos, (float(c[0]), float(c[1]), 0.55), focal, p)
        print(f"  {name}: cam=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) -> {os.path.basename(p)}")
PY
