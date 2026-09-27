#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Produce one clean BACKGROUND render per scene.
#
# The stale-frame bug is fixed (frames were being read from a reused scratch dir,
# so half of every output came from a previous run with a different camera).  With
# that fixed, these renders reflect the camera and lighting actually requested.
#
# For each of the five ReplicaCAD interiors:
#   * load the stage + its authored prop layout
#   * enable the DECLARED authored lighting (铁律�?
#   * place the camera on the -X/+Y side of the furniture cluster, at 1.5 m
#   * render 1920x1080
#
# The camera is chosen per scene from the furniture bounding box rather than
# hand-picked, so each scene gets a sensible interior view.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scenes_bg"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^BG|^  '
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

R = os.path.join(WS, "models/backgrounds/replicad")
STAGES = ["frl_apartment_stage", "Stage_v3_sc0_staging", "Stage_v3_sc1_staging",
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

def render(tag, stage):
    scratch = tempfile.mkdtemp(prefix="bg_")
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

    # authored lighting, from the config the scene itself declares
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

    # frame the furniture cluster, viewed from a corner
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
    span = float(max(hi - lo))

    # An INTERIOR viewpoint: a modest stand-off, clamped to stay inside the room
    # shell (the stage spans ~13 m, so scaling the distance by the span walks the
    # camera outside and produces an exterior dollhouse shot).
    cam = kb.PerspectiveCamera(focal_length=28.0, sensor_width=36.0)
    d = 3.2
    cx = float(np.clip(c[0] + d * 0.62, -2.20, 4.10))
    cy = float(np.clip(c[1] - d * 0.78, -7.70, 4.40))
    cam.position = (cx, cy, 1.55)
    cam.look_at((float(c[0]), float(c[1]), 0.62))
    scene.camera = cam

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"BG {tag}: props={placed} lights={n} span={span:.1f}m "
          f"cam=({cam.position[0]:.1f},{cam.position[1]:.1f},{cam.position[2]:.1f})")
    print(f"  wrote {p}")

for i, s in enumerate(STAGES):
    render(f"{i:02d}_{s.replace('_staging','')}", s)
PY
