#!/usr/bin/env bash
# Can we use BLENDER'S OWN physics instead of hand-written analytic trajectories?
#
# Why this matters: Kubric drives everything through PyBullet, whose rigid solver
# is unusable here (useMaximalCoordinates=True freezes bodies and makes
# changeDynamics a no-op).  That is why our motions are prescribed analytically --
# which is exactly why a falling object currently cannot bounce or squash.
#
# But Blender ships its own physics: a Bullet-based Rigid Body World, plus Soft
# Body and Cloth solvers, all evaluated INSIDE Blender's depsgraph.  None of them
# go through PyBullet, so the Kubric limitation should not apply.  This test
# checks that in a headless (--background) Blender, i.e. the same mode we render in.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_physics_probe"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^PHYS|^  '
import sys, os, tempfile
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
os.makedirs(OUT, exist_ok=True)

N = 24
scratch = tempfile.mkdtemp(prefix="phys_")
scene = kb.Scene(resolution=(640, 360), frame_start=0, frame_end=N - 1,
                 frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=16, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
print("PHYS renderer ready")

# --- a plain floor and a falling cube, added straight through bpy -------------
bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "floor"
floor.data.materials.append(bpy.data.materials.new("floormat"))

bpy.ops.mesh.primitive_cube_add(size=0.3, location=(0, 0, 1.2))
cube = bpy.context.active_object
cube.name = "cube"

# --- Blender's own Rigid Body World -----------------------------------------
# NB: scene.rigidbody_world is None until a world is explicitly added.
if bpy.context.scene.rigidbody_world is None:
    bpy.ops.rigidbody.world_add()
rbw = bpy.context.scene.rigidbody_world
rbw.enabled = True
rbw.point_cache.frame_start = 0
rbw.point_cache.frame_end = N - 1
print("PHYS rigid body world added")

bpy.context.view_layer.objects.active = floor
bpy.ops.rigidbody.object_add(type="PASSIVE")
floor.rigid_body.collision_shape = "MESH"

bpy.context.view_layer.objects.active = cube
bpy.ops.rigidbody.object_add(type="ACTIVE")
cube.rigid_body.collision_shape = "BOX"
cube.rigid_body.restitution = 0.6        # bouncy
cube.rigid_body.friction = 0.5
cube.rigid_body.mass = 0.2

# --- SOFT BODY: does the solver exist and can it be driven headless? ---------
soft_ok = "n/a"
try:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0.6, 0, 1.0))
    soft = bpy.context.active_object
    soft.name = "soft"
    bpy.context.view_layer.objects.active = soft
    bpy.ops.object.modifier_add(type="SOFT_BODY")
    sb = soft.modifiers["Softbody"]
    sb.settings.mass = 1.0
    sb.settings.use_goal = True
    soft.soft_body = None  # ensure attribute exists
    soft_ok = "modifier added"
except Exception as e:
    soft_ok = f"FAILED: {type(e).__name__}: {e}"
print(f"PHYS soft body probe: {soft_ok}")

# --- step the depsgraph and record the cube's height ------------------------
zs = []
for f in range(N):
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()
    zs.append(round(float(cube.matrix_world.translation.z), 4))
print(f"PHYS cube z per frame: {zs}")

z = np.array(zs)
turns = int(np.sum(np.diff(np.sign(np.diff(z))) > 0))
print(f"  start z={z[0]:.3f}  end z={z[-1]:.3f}  min z={z.min():.3f}")
print(f"  direction reversals (bounces) = {turns}")
print(f"  VERDICT: {'PHYSICS RUNS HEADLESS' if z.min() < z[0] - 0.5 else 'NO FALL DETECTED'}")

p = os.path.join(OUT, "z_trace.txt")
open(p, "w").write("\n".join(str(v) for v in zs))
print(f"PHYS wrote {p}")
PY
