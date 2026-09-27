#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build the turntable as a proper asset: mesh + URDF + manifest.
#
# Kubric's fork has no Cylinder primitive (only Cube, Sphere, FileBasedObject,
# SoftBody), so the disc is supplied the same way the GSO actors are: a mesh for
# rendering plus a URDF for physics.  The URDF uses
#     <cylinder radius="R" length="T"/>
# which PyBullet turns into an EXACT cylinder collision shape -- the disc rotates
# smoothly instead of jittering on a faceted hull.
#
# Output: assets/objects/turntable/{visual,collision,license}/ + asset.yaml
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$REPO" "$WS" <<'PY' 2>&1 | grep -E '^TT|^  '
import sys, os, tempfile
REPO = sys.argv[1]
WS = sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.renderer import Blender
import bpy
import math

RADIUS = float(os.environ.get("TT_RADIUS", "0.55"))
THICK = float(os.environ.get("TT_THICK", "0.03"))
SEGS = 128

dst = os.path.join(REPO, "assets/objects/turntable")
os.makedirs(os.path.join(dst, "visual"), exist_ok=True)
os.makedirs(os.path.join(dst, "collision"), exist_ok=True)
os.makedirs(os.path.join(dst, "license"), exist_ok=True)

# --- mesh ------------------------------------------------------------------
scratch = tempfile.mkdtemp(prefix="tt_")
scene = kb.Scene(resolution=(32, 32), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.mesh.primitive_cylinder_add(vertices=SEGS, radius=RADIUS, depth=THICK,
                                    location=(0, 0, 0))
cyl = bpy.context.active_object
cyl.name = "turntable"
bpy.ops.object.shade_smooth()

obj_path = os.path.join(dst, "visual/model.obj")
bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True,
                      forward_axis="Y", up_axis="Z")
print(f"TT mesh  : {obj_path}  ({os.path.getsize(obj_path)/1024:.0f} KB)")

# --- URDF with a true cylinder collision -----------------------------------
urdf = f'''<?xml version="1.0"?>
<robot name="turntable">
  <link name="base">
    <inertial>
      <origin xyz="0 0 0" />
      <mass value="2.0" />
      <inertia ixx="{(2.0)*(3*RADIUS*RADIUS+THICK*THICK)/12:.8f}" ixy="0" ixz="0"
               iyy="{(2.0)*(3*RADIUS*RADIUS+THICK*THICK)/12:.8f}" iyz="0"
               izz="{(2.0)*RADIUS*RADIUS/2:.8f}" />
    </inertial>
    <visual>
      <origin xyz="0 0 0" />
      <geometry>
        <mesh filename="../visual/model.obj" />
      </geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0" />
      <geometry>
        <cylinder radius="{RADIUS}" length="{THICK}" />
      </geometry>
    </collision>
  </link>
</robot>
'''
open(os.path.join(dst, "collision/model.urdf"), "w").write(urdf)
print(f"TT urdf  : cylinder r={RADIUS} length={THICK} (exact primitive collision)")

# --- manifest --------------------------------------------------------------
asset = f"""version: 1
id: turntable
kind: object
category: cylinder

source: generated procedurally for this project
license: CC0 (project-generated; no third-party content)
license_note: built as a URDF cylinder so PyBullet has an exact disc collision

quality:
  primitive: cylinder
  radius_m: {RADIUS}
  thickness_m: {THICK}
  segments: {SEGS}

visual:
  mesh: visual/model.obj
  size: [{2*RADIUS:.6f}, {2*RADIUS:.6f}, {THICK:.6f}]
  scale: [1.0, 1.0, 1.0]

visual_transform:
  x_rotation_degrees: 0.0
  center_mesh_origin: false

initial_orientation:
  policy: fixed_authored_upright
  quaternion_wxyz: [1.0, 0.0, 0.0, 0.0]

collision:
  type: cylinder
  simulation: collision/model.urdf
  radius: {RADIUS}
  half_extents: [{RADIUS:.6f}, {RADIUS:.6f}, {THICK/2:.6f}]
  support_height: {THICK/2:.6f}
  footprint_radius: {RADIUS:.6f}

physics:
  mass_range: [1.0, 3.0]
  friction_range: [0.80, 1.30]
  restitution_range: [0.0, 0.05]

# A turntable is scenery the actor rides on, not a subject itself.
allowed_scenarios: []
"""
open(os.path.join(dst, "asset.yaml"), "w").write(asset)
open(os.path.join(dst, "license/SOURCE.md"), "w").write(
    "# Turntable\n\nGenerated procedurally for this project (URDF cylinder + mesh).\n"
    "No third-party content; no license restrictions.\n")
print(f"TT asset : {dst}")
print("  files:", ", ".join(sorted(os.listdir(dst))))

# --- verify the URDF loads and reports a cylinder collision ----------------
import pybullet as pbc
cid = pbc.connect(pbc.DIRECT)
b = pbc.loadURDF(os.path.join(dst, "collision/model.urdf"))
print(f"TT pybullet: loaded body={b}, base mass={pbc.getDynamicsInfo(b, -1)[0]:.2f} kg")
pbc.disconnect()
PY
