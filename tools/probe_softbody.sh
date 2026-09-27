#!/usr/bin/env bash
# Soft-body check, corrected.
#
# The previous probe failed on `obj.soft_body = None` -- that attribute is
# read-only; the modifier itself had already been added successfully.  Settings
# live on modifiers["Softbody"].settings.
#
# If Blender's soft-body solver runs headless, a falling plush toy can actually
# squash on impact instead of landing rigidly -- which is the realism the review
# asked for, and it costs us no PyBullet involvement at all.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_physics_probe"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^SOFT|^  '
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
import bpy
os.makedirs(OUT, exist_ok=True)

N = 30
scratch = tempfile.mkdtemp(prefix="soft_")
scene = kb.Scene(resolution=(480, 270), frame_start=0, frame_end=N - 1,
                 frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
renderer = Blender(scene, scratch, samples_per_pixel=8, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
print("SOFT ok renderer")

# floor
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "floor"
bpy.context.view_layer.objects.active = floor
bpy.ops.rigidbody.object_add(type="PASSIVE")
floor.rigid_body.collision_shape = "MESH"

# a sphere with a soft body modifier, dropped from 0.8 m
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0, 0, 0.8))
soft = bpy.context.active_object
soft.name = "soft"
bpy.ops.object.shade_smooth()

bpy.context.view_layer.objects.active = soft
bpy.ops.object.modifier_add(type="SOFT_BODY")
sb = soft.modifiers["Softbody"]
print(f"SOFT modifier present: {sb.name}  type={sb.type}")

st = sb.settings
st.mass = 1.0
st.use_goal = True          # keep the rest shape -> behaves like a soft solid
st.goal_default = 0.5       # partial goal: deforms but recovers
st.goal_friction = 10.0
st.pull = 0.5
st.push = 0.5
st.damping = 5.0
st.speed = 1.0
st.use_edges = True
st.ball_size = 0.03         # self-collision radius
st.ball_stiff = 0.9
soft.modifiers["Softbody"].point_cache.frame_start = 0
soft.modifiers["Softbody"].point_cache.frame_end = N - 1
print(f"SOFT settings mass={st.mass} goal={st.goal_default} speed={st.speed}")

# the floor must be able to collide with the soft body
bpy.context.view_layer.objects.active = floor
bpy.ops.object.modifier_add(type="COLLISION")
col = next(m for m in floor.modifiers if m.type == "COLLISION")
print(f"SOFT floor modifiers: {[(m.name, m.type) for m in floor.modifiers]}")
try:
    col.settings.thickness_outer = 0.02
    col.settings.cloth_friction = 5.0
    print(f"SOFT collision thickness={col.settings.thickness_outer}")
except Exception as e:
    print(f"SOFT collision settings partial: {type(e).__name__}: {e}")

# --- run and measure the vertical squash ------------------------------------
dg = bpy.context.evaluated_depsgraph_get()
rest_dz = None
zs, dzs = [], []
for f in range(N):
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = soft.evaluated_get(dg).to_mesh()
    co = np.array([v.co[:] for v in me.vertices])
    dz = float(co[:, 2].max() - co[:, 2].min())
    zc = float(co[:, 2].mean())
    soft.evaluated_get(dg).to_mesh_clear()
    if f == 0:
        rest_dz = dz
    zs.append(round(zc, 4))
    dzs.append(round(dz / rest_dz, 4) if rest_dz else 0)

print(f"SOFT centre z: {zs[:6]} ... {zs[-4:]}")
print(f"SOFT vertical extent / rest extent: {dzs[:6]} ... {dzs[-4:]}")
squash = min(dzs)
print(f"  rest extent ratio = 1.0;  min ratio = {squash:.3f}")
print(f"  => squash on impact = {100*(1-squash):.1f}%")
print(f"  VERDICT: {'SOFT BODY DEFORMS -> usable' if squash < 0.97 else 'no deformation seen'}")
PY
