#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# TURNTABLE: build it procedurally and prove the physics carries an object.
#
# No turntable exists in our assets (GSO: only DVDs, saucers, trays; Poly Haven:
# 521 models, none a turntable).  Building one is also the better choice:
#
#   * a CYLINDER primitive gives PyBullet an exact cylinder collision shape, so
#     the disc spins smoothly.  A scanned mesh would need convex decomposition and
#     would jitter as the faceted hull rotated.
#   * radius/thickness/height are parameters we control, so the disc can be sized
#     to each actor.
#
# How the motion becomes physical: the disc is a KINEMATIC body driven at constant
# angular velocity.  PyBullet resolves FRICTION between disc and actor every step,
# so the actor is carried around rather than being animated along a circle.  That
# is the whole point -- "it goes in a circle" becomes a consequence of contact and
# friction, not a scripted path.
#
# This probe checks, on the real engine:
#   1. a disc can be made kinematic and spun
#   2. an object placed on it is actually carried (delta angle > 0)
#   3. it travels roughly with the disc (slip ratio < 1)
#   4. it stays ON the disc (radial distance bounded)
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_turntable"
rm -rf "$OUT"; mkdir -p "$OUT"

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

pb_client = __import__("pybullet")

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
DISC_R = 0.55          # disc radius (m)
DISC_T = 0.03          # disc thickness (m)
DISC_Z = 0.05          # disc top surface height (m)
OMEGA = 1.2            # rad/s
FPS, N = 24, 48

scratch = tempfile.mkdtemp(prefix="tt_")
scene = kb.Scene(resolution=(960, 540), frame_start=0, frame_end=N - 1,
                 frame_rate=FPS, step_rate=240, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
print("TT renderer ready")

# --- ground ---------------------------------------------------------------
ground = kb.Cube(name="ground", scale=(4, 4, 0.1), position=(0, 0, -0.1),
                 static=True, segmentation_id=1)
ground.material = kb.PrincipledBSDFMaterial(color=(0.45, 0.45, 0.45, 1.0))
scene += ground

# --- turntable disc -------------------------------------------------------
# rbCylinder collision; kinematic so its motion is prescribed by us but its
# INTERACTION with the actor is resolved by the solver.
disc = kb.Cylinder(name="turntable", radius=DISC_R, depth=DISC_T,
                   position=(0, 0, DISC_Z - DISC_T / 2.0),
                   static=True, segmentation_id=3)
disc.material = kb.PrincipledBSDFMaterial(color=(0.25, 0.26, 0.30, 1.0),
                                          roughness=0.55, metallic=0.35)
scene += disc

# --- actor on the disc ----------------------------------------------------
meta = json.load(open(os.path.join(GSO, "data.json")))
b = meta["kwargs"]["bounds"]; rest = -b[0][2]
r0 = 0.30                       # start offset from the axis
obj = kb.FileBasedObject(
    name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
    render_filename=os.path.join(GSO, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
    scale=1.0, position=(r0, 0.0, DISC_Z + rest), segmentation_id=2)
scene += obj

# --- make the disc kinematic and drive it ---------------------------------
client = sim._physics_client
body_id = disc.linked_objects[sim]
pb_client.changeDynamics(body_id, -1, mass=0, lateralFriction=1.2,
                         restitution=0.0, spinningFriction=0.02,
                         rollingFriction=0.005)

states = []
for f in range(N):
    t = f / float(FPS)
    ang = OMEGA * t
    quat = (0.0, 0.0, math.sin(ang / 2.0), math.cos(ang / 2.0))
    pb_client.resetBasePositionAndOrientation(body_id, [0, 0, DISC_Z - DISC_T / 2.0], quat)
    pb_client.resetBaseVelocity(body_id, [0, 0, 0], [0, 0, OMEGA])
    sim.step()
    pos, o = pb_client.getBasePositionAndOrientation(obj.linked_objects[sim])
    states.append((f, t, float(pos[0]), float(pos[1]), float(pos[2])))

print(f"TT disc r={DISC_R} thickness={DISC_T} omega={OMEGA} rad/s  actor starts at r={r0}")
print("TT frame-by-frame (x, y, radius, angle deg):")
for f, t, x, y, z in states[::8]:
    r = math.hypot(x, y)
    a = math.degrees(math.atan2(y, x))
    print(f"    f{f:02d} t={t:.2f}s  ({x:+.3f},{y:+.3f})  r={r:.3f}  ang={a:+7.1f}  z={z:.3f}")

xs = np.array([s[2] for s in states]); ys = np.array([s[3] for s in states])
rs = np.hypot(xs, ys)
ang = np.unwrap(np.arctan2(ys, xs))
swept = math.degrees(ang[-1] - ang[0])
expected = math.degrees(OMEGA * (N - 1) / FPS)
print()
print(f"TT swept angle  : {swept:.1f} deg   (disc turned {expected:.1f} deg)")
print(f"TT radial drift : r {rs[0]:.3f} -> {rs[-1]:.3f} m  (min {rs.min():.3f} max {rs.max():.3f})")
print(f"TT stayed on disc: {bool(rs.max() < DISC_R)}")
print(f"TT carried by friction: {bool(abs(swept) > 30)}")
if expected:
    print(f"TT slip ratio   : {abs(swept) / abs(expected):.2f}  (1.0 = moves with the disc)")

# --- one render so the rig can be seen ------------------------------------
key = kb.DirectionalLight(name="key", position=(1.6, -2.0, 3.0), intensity=2.6)
key.look_at((0, 0, 0.15)); scene += key
renderer._set_ambient_light_color((0.45, 0.45, 0.48, 1.0))
renderer._set_background_color((0.55, 0.60, 0.68, 1.0))
cam = kb.PerspectiveCamera(focal_length=40.0, sensor_width=36.0)
cam.position = (1.35, -1.55, 1.05)
cam.look_at((0.0, 0.0, 0.20))
scene.camera = cam
out = renderer.render([0], return_layers=("rgba",))
img = np.array(out["rgba"], copy=True)[0]
cv2.imwrite(os.path.join(OUT, "turntable_rig.png"), img[..., :3][..., ::-1])
print(f"TT wrote {OUT}/turntable_rig.png")
PY
