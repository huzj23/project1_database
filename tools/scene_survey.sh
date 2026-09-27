#!/usr/bin/env bash
# Scene survey, take 2.
#
# The first attempt aimed the camera by hand and ended up staring at a wall.
# Here the camera is derived from the actual content: compute the bounding box of
# whatever was loaded (stage, or stage+props) and put the lens on a diagonal
# looking at its centre.
#
# Renders, for comparison:
#   01  frl_apartment_stage, empty          (what our D batch used)
#   02  frl_apartment_stage + apt_0 props   (furnished)
#   03..06  Stage_v3_sc0..sc3 + their props (the other four interiors)
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scene_survey"
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

def scene_json_for(stage_name):
    """Pick an authored scene instance that uses this stage."""
    cands = sorted(glob.glob(os.path.join(R, "configs/scenes/*.scene_instance.json")))
    for c in cands:
        try:
            cfg = json.load(open(c))
        except Exception:
            continue
        if os.path.basename(cfg.get("stage_instance", {}).get("template_name", "")) == stage_name:
            return c, cfg
    return None, None

def bounds(objs):
    lo = np.array([1e18] * 3); hi = np.array([-1e18] * 3)
    for o in objs:
        if o.type != "MESH":
            continue
        mw = np.array(o.matrix_world)
        loc = np.array([list(c) for c in o.bound_box], dtype=float)
        w = loc @ mw[:3, :3].T + mw[:3, 3]
        lo = np.minimum(lo, w.min(axis=0)); hi = np.maximum(hi, w.max(axis=0))
    return lo, hi

def render(tag, stage_glb, scene_json, cam_dir, dist_k, height_k):
    scratch = tempfile.mkdtemp(prefix="sc_")
    scene = kb.Scene(resolution=(960, 540), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=24, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    before = {o.name for o in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=stage_glb)
    stage_objs = [o for o in bpy.data.objects if o.name not in before]
    lo, hi = bounds(stage_objs)

    placed = 0
    if scene_json:
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
            new = [o for o in bpy.data.objects if o.name not in b2]
            tr = inst.get("translation", [0, 0, 0])
            # habitat is Y-up; the stage import already went to Z-up, so use the
            # same mapping: (x, y, z)_habitat -> (x, -z, y)_blender
            for o in new:
                if o.parent is None:
                    o.location = (o.location.x + float(tr[0]),
                                  o.location.y - float(tr[2]),
                                  o.location.z + float(tr[1]))
            placed += 1

    allm = [o for o in bpy.data.objects if o.type == "MESH"]
    lo2, hi2 = bounds(allm)
    # use the furniture extent when we have props (the room shell is much bigger)
    lo_u, hi_u = (lo2, hi2) if placed else (lo, hi)
    c = (lo_u + hi_u) / 2.0
    span = float(max(hi_u - lo_u))
    dist = span * dist_k

    renderer._set_ambient_light_color((0.60, 0.60, 0.62, 1.0))
    renderer._set_background_color((0.35, 0.40, 0.48, 1.0))
    sun = kb.DirectionalLight(name="sun", position=(c[0] + 4, c[1] - 5, c[2] + 7),
                              intensity=2.6)
    sun.look_at((float(c[0]), float(c[1]), float(c[2]))); scene += sun
    fill = kb.RectAreaLight(name="fill", position=(c[0] - 3, c[1] - 3, c[2] + 3),
                            intensity=300.0, width=5.0, height=4.0)
    fill.look_at((float(c[0]), float(c[1]), float(c[2]))); scene += fill

    cam = kb.PerspectiveCamera(focal_length=26.0, sensor_width=36.0)
    cam.position = (float(c[0] + cam_dir[0] * dist),
                    float(c[1] + cam_dir[1] * dist),
                    float(c[2] + span * height_k))
    cam.look_at((float(c[0]), float(c[1]), float(c[2])))
    scene.camera = cam

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"SC {tag}: props={placed} span={span:.1f}m dist={dist:.1f}m "
          f"centre=({c[0]:.1f},{c[1]:.1f},{c[2]:.1f})")
    print(f"  wrote {p}")

stages = ["frl_apartment_stage", "Stage_v3_sc0_staging", "Stage_v3_sc1_staging",
          "Stage_v3_sc2_staging", "Stage_v3_sc3_staging"]
for i, s in enumerate(stages):
    glb = os.path.join(R, "stages", f"{s}.glb")
    sj, _ = scene_json_for(s)
    tag = f"{i+1:02d}_{s.replace('_staging','')}"
    if i == 0:
        render(f"{tag}_empty", glb, None, (0.72, -0.90), 0.95, 0.55)
    render(f"{tag}_furnished", glb, sj, (0.72, -0.90), 0.95, 0.55)
PY
