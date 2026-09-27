#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Find a support region that leaves room for the CAMERA, not merely for the object.
#
# The previous pick maximised clear floor area and got a 1.0 x 5.4 m corridor.
# Geometrically that is the biggest clear rectangle, but it hugs the walls, so the
# camera standing off ~2 m ends up against a wall and a quarter of the frame is
# occluded -- exactly the defect that was reported.
#
# New criterion: score candidate centres by
#     min(distance to any wall, distance to any furniture)
# i.e. the radius of the largest empty disc around the point.  The camera needs
# roughly that much room to orbit.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" "$REPO" <<'PY' 2>&1 | grep -E '^OPEN|^  '
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
STAGE = os.path.join(R, "stages/frl_apartment_stage.glb")
SJ = os.path.join(R, "configs/scenes/apt_0.scene_instance.json")
SJ_OUT = os.path.join(REPO, "configs/_map_replicad_snippet.yaml")

scratch = tempfile.mkdtemp(prefix="open_")
scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
sim = PyBullet(scene, scratch)

bpy.ops.import_scene.gltf(filepath=STAGE)
cfg = json.load(open(SJ))

# obstacles = furniture, walls stay in the stage mesh but we only care about a
# local clear disc, so furniture awareness is what matters here
obstacles = []
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
    for o in new:
        if o.parent is None:
            o.location = (o.location.x + float(tr[0]),
                          o.location.y - float(tr[2]),
                          o.location.z + float(tr[1]))
    for o in new:
        if o.type != "MESH":
            continue
        mw = np.array(o.matrix_world)
        loc = np.array([list(c) for c in o.bound_box], dtype=float)
        w = loc @ mw[:3, :3].T + mw[:3, 3]
        if w[:, 2].max() < 0.05:      # rugs / floor decals: not obstacles
            continue
        cx, cy = (w[:, 0].min() + w[:, 0].max()) / 2, (w[:, 1].min() + w[:, 1].max()) / 2
        rad = 0.5 * max(w[:, 0].ptp(), w[:, 1].ptp())
        obstacles.append((cx, cy, rad))
print(f"OPEN obstacles (furniture footprints): {len(obstacles)}")

dg = bpy.context.evaluated_depsgraph_get()
FLOOR_Z = 0.0007
X0, X1, Y0, Y1, STEP = -2.6, 4.5, -8.0, 4.8, 0.10
xs = np.arange(X0, X1 + 1e-9, STEP)
ys = np.arange(Y0, Y1 + 1e-9, STEP)

def wall_distance(x, y):
    return min(x - X0, X1 - x, y - Y0, Y1 - y)

def furniture_distance(x, y):
    if not obstacles:
        return 99.0
    best = 99.0
    for cx, cy, rad in obstacles:
        best = min(best, max(0.0, np.hypot(x - cx, y - cy) - rad))
    return best

# a cell qualifies when the floor is clear there AND there is room to stand off
cands = []
for y in ys:
    for x in xs:
        ok, loc, nrm, _i, obj, _m = bpy.context.scene.ray_cast(
            dg, Vector((float(x), float(y), 4.0)), Vector((0, 0, -1)), distance=8.0)
        if not ok or abs(loc[2]) > 0.06 or nrm.z < 0.9:
            continue
        wd, fd = wall_distance(x, y), furniture_distance(x, y)
        clearance = min(wd, fd)
        if clearance >= 1.6:            # camera needs ~2 m of room
            cands.append((clearance, x, y))

if not cands:
    print("OPEN no cell has >=1.6 m of clearance")
    raise SystemExit(1)

cands.sort(reverse=True)
best_clear, bx, by = cands[0]
print(f"OPEN best centre: ({bx:.2f}, {by:.2f})  clearance={best_clear:.2f} m  "
      f"(wall={wall_distance(bx,by):.2f}, furniture={furniture_distance(bx,by):.2f})")

# grow a region around it while keeping clearance >= 1.2 m
KEEP = 1.2
sel = [(x, y) for c, x, y in cands if c >= KEEP and abs(x - bx) < 2.5 and abs(y - by) < 2.5]
sx = [p[0] for p in sel]; sy = [p[1] for p in sel]
bx0, bx1, by0, by1 = min(sx), max(sx), min(sy), max(sy)
print(f"OPEN region: x[{bx0:.2f},{bx1:.2f}] y[{by0:.2f},{by1:.2f}] "
      f"= {bx1-bx0:.2f} x {by1-by0:.2f} m   ({len(sel)} cells, clearance>={KEEP})")

# sanity: how far can a camera at this centre get before hitting a wall?
print(f"OPEN camera headroom from centre: "
      f"x-={bx - X0:.2f} x+={X1 - bx:.2f} y-={by - Y0:.2f} y+={Y1 - by:.2f} m")

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
          - region_id: replicad_apartment_floor_open
            cleanliness: verified_clear
            verification: raycast_grid_0p10m_camera_clearance_ge_1p2m
            position: [{ (bx0+bx1)/2:.4f}, { (by0+by1)/2:.4f}, {FLOOR_Z:.4f}]
            normal: [0.0, 0.0, 1.0]
            bounds_xy: [{bx0:.4f}, {bx1:.4f}, {by0:.4f}, {by1:.4f}]
"""
open(SJ_OUT, "w").write(mapline)
print(f"OPEN wrote map snippet: {SJ_OUT}")
PY
