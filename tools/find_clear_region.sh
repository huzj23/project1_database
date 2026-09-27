#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# P1.2  Find and verify a CLEAR floor region in the ReplicaCAD apartment, then
#       emit the map entry in the mentor's maps.yaml format.
#
# His map rules require `cleanliness: verified_clear` with a recorded method.
# The method here: cast a downward ray over a grid; a cell is "clear" when the
# first hit is the floor itself (not furniture, not a stair riser).  Then grow
# the largest all-clear rectangle.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^CLR|^  '
import sys, os, json, tempfile
WS, REPO = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy
from mathutils import Vector

R = os.path.join(WS, "models/backgrounds/replicad")
scratch = tempfile.mkdtemp(prefix="clr_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
sim = PyBullet(scene, scratch)

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
print("CLR world loaded with furniture")

dg = bpy.context.evaluated_depsgraph_get()

# Probe the room footprint on a 0.10 m grid.
X0, X1 = -2.6, 4.5
Y0, Y1 = -8.0, 4.8
STEP = 0.10
xs = np.arange(X0, X1 + 1e-9, STEP)
ys = np.arange(Y0, Y1 + 1e-9, STEP)
floor_z = None
clear = np.zeros((len(ys), len(xs)), dtype=bool)
zmap = np.full((len(ys), len(xs)), np.nan)

for j, y in enumerate(ys):
    for i, x in enumerate(xs):
        ok, loc, nrm, _idx, obj, _m = bpy.context.scene.ray_cast(
            dg, Vector((float(x), float(y), 4.0)), Vector((0, 0, -1)), distance=8.0)
        if not ok:
            continue
        # floor hit: horizontal surface near z=0 whose object name says "floor"
        nm = obj.name.lower() if obj else ""
        if abs(loc[2]) < 0.06 and nrm.z > 0.9 and ("floor" in nm or "stage" in nm):
            clear[j, i] = True
            zmap[j, i] = float(loc[2])

n_clear = int(clear.sum())
zs = zmap[np.isfinite(zmap)]
fz = float(np.median(zs)) if len(zs) else 0.0
print(f"CLR clear floor cells: {n_clear} / {clear.size}   floor_z median = {fz:.4f}")

# Grow the largest all-clear axis-aligned rectangle (greedy row band).
best = (0, None)
for j0 in range(clear.shape[0]):
    run = np.ones(clear.shape[1], dtype=bool)
    for j1 in range(j0, clear.shape[0]):
        run &= clear[j1]
        if not run.any():
            break
        # longest run of True in `run`
        idx = np.flatnonzero(np.diff(np.concatenate(([0], run.view(np.int8), [0]))))
        if len(idx) >= 2:
            starts, ends = idx[0::2], idx[1::2]
            k = int(np.argmax(ends - starts))
            w, hgt = int(ends[k] - starts[k]), (j1 - j0 + 1)
            area = w * hgt
            if area > best[0]:
                best = (area, (j0, j1, int(starts[k]), int(ends[k] - 1)))

if best[1] is None:
    print("CLR no clear rectangle found")
    raise SystemExit(1)

j0, j1, i0, i1 = best[1]
bx = (float(xs[i0]), float(xs[i1]))
by = (float(ys[j0]), float(ys[j1]))
w, h = bx[1] - bx[0], by[1] - by[0]
print(f"CLR largest clear rect: x[{bx[0]:.2f},{bx[1]:.2f}] y[{by[0]:.2f},{by[1]:.2f}]"
      f"  = {w:.2f} x {h:.2f} m")
cx, cy = (bx[0] + bx[1]) / 2, (by[0] + by[1]) / 2
print(f"CLR centre = ({cx:.2f}, {cy:.2f})  floor_z = {fz:.4f}")
# leave a margin so the object never starts on the boundary
m = 0.25
print(f"CLR usable with {m} m margin: x[{bx[0]+m:.2f},{bx[1]-m:.2f}] "
      f"y[{by[0]+m:.2f},{by[1]-m:.2f}]")

# ---- emit the environment asset + map entry -------------------------------
envdir = os.path.join(REPO, "assets/environments/replicad_apartment")
os.makedirs(os.path.join(envdir, "license"), exist_ok=True)
os.makedirs(os.path.join(envdir, "collision/surfaces"), exist_ok=True)

open(os.path.join(envdir, "asset.yaml"), "w").write(f"""version: 1
id: replicad_apartment
kind: environment
category: environment

source: ReplicaCAD (FAIR / Meta), frl_apartment_stage + apt_0 layout
license: CC BY-NC 4.0
license_note: NonCommercial; academic use permitted. See license/SOURCE.md

quality:
  description: Scanned studio apartment, furnished from the authored apt_0 layout
  stage_mesh_objects: 20
  prop_instances: 113
  preserved_source_lights: 7
  authored_lighting_config: configs/lighting/frl_apartment_stage.lighting_config.json

visual:
  mesh: visual/scene.glb
  object_name: environment
  size: [{bx[1]-bx[0]:.6f}, {by[1]-by[0]:.6f}, 3.13]

# The floor is flat; a box proxy over the verified-clear region is sufficient.
collision:
  type: box
  center: [{cx:.6f}, {cy:.6f}, {fz - 0.05:.6f}]
  half_extents: [{(bx[1]-bx[0])/2:.6f}, {(by[1]-by[0])/2:.6f}, 0.05]

physics:
  mass_range: [0.0, 0.0]
  friction_range: [0.45, 0.75]
  restitution_range: [0.0, 0.1]

render:
  lighting_source: authored_config_only
  authored_config: configs/lighting/frl_apartment_stage.lighting_config.json

allowed_scenarios: [rolling, constant_force, free_fall]
""")

open(os.path.join(envdir, "license/SOURCE.md"), "w").write(
"""# ReplicaCAD

Source: ReplicaCAD dataset (FAIR / Meta), `frl_apartment_stage` + `apt_0` layout.
License: CC BY-NC 4.0 (NonCommercial). Academic research use permitted.
See the project license notes for the full analysis.
""")

mapline = f"""
  replicad_apartment:
    environment_asset_id: replicad_apartment
    surface_groups:
      - surface_type: floor
        object_extent_range_m: [0.03, 0.35]
        edge_margin: 0.25
        clearance: 0.4
        collision_thickness: 0.05
        regions:
          - region_id: replicad_apartment_floor_clear
            cleanliness: verified_clear
            verification: raycast_grid_0p10m_furniture_excluded
            position: [{cx:.4f}, {cy:.4f}, {fz:.4f}]
            normal: [0.0, 0.0, 1.0]
            bounds_xy: [{bx[0]:.4f}, {bx[1]:.4f}, {by[0]:.4f}, {by[1]:.4f}]
"""
p = os.path.join(REPO, "configs/_map_replicad_snippet.yaml")
open(p, "w").write(mapline)
print(f"CLR wrote env asset: {envdir}")
print(f"CLR wrote map snippet: {p}")
PY
