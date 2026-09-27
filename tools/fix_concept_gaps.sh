#!/usr/bin/env bash
# Fix the two remaining realism gaps:
#   A) GSO texture missing -- we set obj.material, overwriting the .mtl that
#      carries map_Kd texture.png.  Test: do NOT override the material.
#   B) no visible shadow -- the HDRI ambient floods the scene.  Test: stronger
#      key light and a weaker HDRI ambient.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_concept3"
rm -rf "$OUT"

"$PY" - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^FIX|^  '
import sys, os, json, tempfile
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
import phyco_motions as pm
import phyco_backdrops as pb
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy, cv2
os.makedirs(OUT, exist_ok=True)

GSO = "Sootheze_Cold_Therapy_Elephant"
GD = os.path.join(WS, "models/gso", GSO)
d = json.load(open(os.path.join(GD, "data.json")))
b = d["kwargs"]["bounds"]; rest_z = -b[0][2]
span = [b[1][i] - b[0][i] for i in range(3)]

def build(keep_material: bool, key_intensity: float, hdri_strength: float, tag: str):
    scratch = tempfile.mkdtemp(prefix=f"fix_{tag}_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(6, 6, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.55, 0.55, 1.0), roughness=0.85)
    scene += ground
    mat, _ = pb.pbr_material(kb, "concrete_floor_worn_001", "concrete_textures", uv_scale=6.0)
    pb.apply_bpy_material(renderer, ground, mat)

    pb.enable_hdri_file(renderer, "empty_warehouse_01", strength=hdri_strength)

    key = kb.RectAreaLight(name="Key", position=(1.6, -1.4, 2.2),
                           intensity=key_intensity, width=2.2, height=2.2,
                           color=(1.0, 0.97, 0.92))
    key.look_at((0, 0, rest_z)); scene += key

    obj = kb.FileBasedObject(
        name=GSO, simulation_filename=os.path.join(GD, "object.urdf"),
        render_filename=os.path.join(GD, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=d["kwargs"]["mass"],
        scale=1.0, position=(0.0, 0.0, rest_z), segmentation_id=2)
    if not keep_material:
        obj.material = kb.PrincipledBSDFMaterial(color=(0.85, 0.72, 0.62, 1.0))
    scene += obj

    # report what materials exist on the actor
    bo = obj.linked_objects.get(renderer)
    mats = [m.name for m in bo.data.materials] if bo and hasattr(bo, "data") else []
    has_img = any(
        n.type == "TEX_IMAGE" and n.image
        for m in (bo.data.materials if bo and hasattr(bo, "data") else [])
        if m and m.use_nodes for n in m.node_tree.nodes)
    print(f"FIX [{tag}] keep_material={keep_material} key={key_intensity:.0f} "
          f"hdri={hdri_strength}  actor materials={mats}  has_image_tex={has_img}")

    spec = pm.CircularSpec(radius=0.40, period_s=5.0,
                           center=(0.0, 0.0, rest_z), axis="z")
    states = pm.apply_circular(kb, obj, spec, 8, 24.0, [0.0, 0.0, 0.0])
    pc.auto_frame_camera(kb, scene, [[states[f]["position"][0], states[f]["position"][1],
                                      rest_z + span[2] / 2] for f in range(8)],
                         (0.0, 0.0, rest_z + span[2] * 0.5),
                         elevation_deg=11.0, azimuth_deg=-62.0, margin=0.18,
                         start_distance=1.6, focal_length=55.0, sensor_width=36.0)
    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"fix_{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"  wrote {p}")

# A: keep the imported .mtl (texture), normal lighting
build(keep_material=True,  key_intensity=900.0,  hdri_strength=1.1, tag="A_tex")
# B: keep texture AND push the key light / damp the ambient so a shadow shows
build(keep_material=True,  key_intensity=4000.0, hdri_strength=0.35, tag="B_shadow")
PY
