#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Verify the turntable physics: does friction actually carry the actor?
#
# The disc is loaded from the asset just built (URDF cylinder) and driven as a
# KINEMATIC body at constant angular velocity.  PyBullet then resolves contact and
# friction every step.  We measure whether the actor:
#   * is carried around (swept angle > 0)
#   * moves roughly with the disc (slip ratio near 1)
#   * stays on the disc (radial distance bounded by the radius)
#   * if it slides off, at what spin rate -- which sets the usable speed range
#
# A small angular-velocity sweep is included because the answer to "how fast can
# it spin before the actor is thrown off" is a physical property of the friction
# coefficient, not something to guess.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_turntable"
mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^TT|^  '
import sys, os, json, tempfile, math
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
import pybullet as pbc

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT_URDF = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main",
                       "assets/objects/turntable/collision/model.urdf")
DISC_R, DISC_T, DISC_Z = 0.55, 0.03, 0.05
FPS, N = 24, 48

def run(omega, r0=0.30, friction=1.2):
    scratch = tempfile.mkdtemp(prefix="ttp_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=N - 1,
                     frame_rate=FPS, step_rate=240, gravity=(0, 0, -9.81))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(4, 4, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    scene += ground

    disc = kb.FileBasedObject(
        name="turntable", asset_id="turntable",
        simulation_filename=TT_URDF,
        render_filename=os.path.join(os.path.dirname(TT_URDF), "../visual/model.obj"),
        scale=(1.0, 1.0, 1.0), static=True, position=(0, 0, DISC_Z - DISC_T / 2.0),
        segmentation_id=3)
    scene += disc

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(r0, 0.0, DISC_Z + rest), segmentation_id=2)
    scene += obj

    did = disc.linked_objects[sim]
    oid = obj.linked_objects[sim]
    print(f"TT   body ids: disc={did} actor={oid}")
    pbc.changeDynamics(did, -1, mass=0, lateralFriction=friction,
                       restitution=0.0, spinningFriction=0.02, rollingFriction=0.005)

    xs, ys, zs = [], [], []
    for f in range(N):
        ang = omega * (f / float(FPS))
        q = (0.0, 0.0, math.sin(ang / 2.0), math.cos(ang / 2.0))
        pbc.resetBasePositionAndOrientation(did, [0, 0, DISC_Z - DISC_T / 2.0], q)
        pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, omega])
        pbc.stepSimulation()
        p, _ = pbc.getBasePositionAndOrientation(oid)
        xs.append(p[0]); ys.append(p[1]); zs.append(p[2])

    xs, ys, zs = np.array(xs), np.array(ys), np.array(zs)
    rs = np.hypot(xs, ys)
    ang = np.unwrap(np.arctan2(ys, xs))
    swept = math.degrees(ang[-1] - ang[0])
    expected = math.degrees(omega * (N - 1) / FPS)
    return dict(omega=omega, swept=swept, expected=expected,
                r0=float(rs[0]), r1=float(rs[-1]), rmax=float(rs.max()),
                on_disc=bool(rs.max() < DISC_R),
                z_end=float(zs[-1]), fell=bool(zs[-1] < DISC_Z - 0.02))

print("TT turntable physics â€?actor placed at r=0.30 m on a 0.55 m disc")
print(f"TT {'omega':>7} {'swept':>9} {'disc':>8} {'slip':>6} {'r_end':>7} {'rmax':>7}  on_disc  fell")
for w in (0.6, 1.2, 2.0, 3.0, 4.5):
    r = run(w)
    slip = abs(r["swept"]) / abs(r["expected"]) if r["expected"] else 0.0
    print(f"TT {w:7.2f} {r['swept']:8.1f}d {r['expected']:7.1f}d {slip:6.2f} "
          f"{r['r1']:7.3f} {r['rmax']:7.3f}  {str(r['on_disc']):>7}  {str(r['fell']):>5}")

print()
print("TT interpretation:")
print("  slip near 1.0  -> the actor is carried by friction, moving with the disc")
print("  slip near 0.0  -> the disc spins underneath and the actor stays put")
print("  on_disc False  -> the actor was flung off (too fast for this friction)")
PY
