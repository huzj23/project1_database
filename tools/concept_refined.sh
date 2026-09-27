#!/usr/bin/env bash
# REFINED CONCEPT using only assets that are proven to work:
#   * GSO scanned object as the actor          (real geometry, proven)
#   * Poly Haven 4K HDRI as the background+light (photoreal panorama, proven)
#   * ground plane with CORRECT texel density  (fixes the blurry-floor problem)
#   * actor RESTING on the ground at its rest height (fixes "floating")
#   * a key light strong enough to cast a readable contact shadow
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_concept2"
rm -rf "$OUT"

"$PY" - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^REF|^  '
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
import cv2, bpy

os.makedirs(OUT, exist_ok=True)
GSO = "Sootheze_Cold_Therapy_Elephant"
GD = os.path.join(WS, "models/gso", GSO)
d = json.load(open(os.path.join(GD, "data.json")))
b = d["kwargs"]["bounds"]
rest_z = -b[0][2]
span = [b[1][i] - b[0][i] for i in range(3)]
print(f"REF object {GSO}  span={np.round(span,3).tolist()}  rest_z={rest_z:.3f}")

N, FPS = 16, 24
scratch = tempfile.mkdtemp(prefix="ref_")
scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=N - 1,
                 frame_rate=FPS, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)

# --- ground: real PBR concrete with enough texel density --------------------
GROUND_M = 12.0                       # world size of the ground plate
UV_SCALE = 6.0                        # 4K tile repeats -> ~1365 texel/m
ground = kb.Cube(name="ground", scale=(GROUND_M / 2, GROUND_M / 2, 0.1),
                 position=(0, 0, -0.1), static=True, segmentation_id=1)
ground.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.55, 0.55, 1.0), roughness=0.85)
scene += ground
mat, mi = pb.pbr_material(kb, "concrete_floor_worn_001", "concrete_textures",
                          uv_scale=UV_SCALE)
if pb.apply_bpy_material(renderer, ground, mat):
    texels_per_m = 4096 * UV_SCALE / GROUND_M
    print(f"REF ground PBR applied  uv_scale={UV_SCALE} -> {texels_per_m:.0f} texel/m")
    print(f"  maps: {list(mi['maps'].keys())}")

# --- background + light: photoreal HDRI -------------------------------------
p = pb.enable_hdri_file(renderer, "empty_warehouse_01", strength=1.1)
print(f"REF hdri background = {p}")

# --- a key light so the actor casts a readable contact shadow ---------------
key = kb.RectAreaLight(name="Key", position=(1.6, -1.4, 2.2),
                       intensity=900.0, width=2.2, height=2.2,
                       color=(1.0, 0.97, 0.92))
key.look_at((0, 0, rest_z))
scene += key
print("REF key softbox added (shadow caster)")

# --- actor: GSO object RESTING on the ground --------------------------------
obj = kb.FileBasedObject(
    name=GSO,
    simulation_filename=os.path.join(GD, "object.urdf"),
    render_filename=os.path.join(GD, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=d["kwargs"]["mass"],
    scale=1.0, position=(0.0, 0.0, rest_z), segmentation_id=2)
obj.material = kb.PrincipledBSDFMaterial(color=(0.85, 0.72, 0.62, 1.0))
scene += obj

spec = pm.CircularSpec(radius=0.40, period_s=5.0,
                       center=(0.0, 0.0, rest_z), axis="z", spin_per_orbit=1.0)
states = pm.apply_circular(kb, obj, spec, N, float(FPS), [0.0, 0.0, 0.0])
print(f"REF motion r={spec.radius} m  v={spec.tangential_speed:.2f} m/s  on floor")

# --- framing ----------------------------------------------------------------
traj = []
for f in range(N):
    q = states[f]["position"]
    h = span[2] / 2
    for dx, dy, dz in ((0, 0, h), (0, 0, -h), (span[0] / 2, 0, 0), (-span[0] / 2, 0, 0)):
        traj.append([q[0] + dx, q[1] + dy, q[2] + dz])
cam_d, fr = pc.auto_frame_camera(
    kb, scene, traj, (0.0, 0.0, rest_z + span[2] * 0.5),
    elevation_deg=11.0, azimuth_deg=-62.0, margin=0.18,
    start_distance=1.6, focal_length=55.0, sensor_width=36.0)
vis_w = 2 * cam_d * np.tan(np.arctan(36 / (2 * 55)))
print(f"REF camera d={cam_d:.2f} m  visible width {vis_w:.2f} m")
print(f"  actor is {100*span[0]/vis_w:.0f}% of frame width")

out = renderer.render(list(range(N)), return_layers=("rgba", "segmentation", "depth"))
out = {k: np.array(v, copy=True) for k, v in out.items()}
rgba = pc.prepare_rgba(out["rgba"])
pc.write_image_sequence(rgba, OUT, "rgba", "png")
print(f"REF wrote {len(rgba)} frames to {OUT}")
PY

echo
ls "$OUT" | head -4
