#!/usr/bin/env bash
# Multiple viewpoints for the four non-apartment interiors, so each room can be
# judged properly rather than from a single angle.
#
# Per scene: a corner view, a lower eye-level view, and a view toward the stairs --
# the three reads that show a room's layout, furniture and depth.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scenes_multi"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^MV|^  '
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
STAGES = ["Stage_v3_sc0_staging", "Stage_v3_sc1_staging",
          "Stage_v3_sc2_staging", "Stage_v3_sc3_staging"]

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
    scratch = tempfile.mkdtemp(prefix="mv_")
    scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)
    bpy.ops.import_scene.gltf(filepath=os.path.join(R, "stages", f"{stage}.glb"))
    sj, cfg = cfg_for(stage)
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
    return scene, renderer, placed, n

# three viewpoints per scene, all inside the room shell
VIEWS = [
    ("a_corner",  (3.35, -6.90, 1.55), (0.60, -3.60, 0.65), 30.0),
    ("b_eye",     (2.20, -2.60, 1.50), (0.90, -5.20, 0.70), 28.0),
    ("c_stairs",  (-1.40, -4.20, 1.60), (1.60, -3.20, 0.85), 26.0),
]

for si, stage in enumerate(STAGES):
    tag = stage.replace("_staging", "")
    scene, renderer, placed, n = build(stage)
    print(f"MV {tag}: props={placed} lights={n}")
    for vname, pos, aim, fl in VIEWS:
        cam = kb.PerspectiveCamera(focal_length=fl, sensor_width=36.0)
        cam.position = pos
        cam.look_at(aim)
        scene.camera = cam
        out = renderer.render([0], return_layers=("rgba",))
        img = np.array(out["rgba"], copy=True)[0]
        p = os.path.join(OUT, f"{si}_{tag}_{vname}.png")
        cv2.imwrite(p, img[..., :3][..., ::-1])
        print(f"  wrote {os.path.basename(p)}")
PY
