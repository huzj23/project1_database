#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Regenerate each GSO asset's URDF from a template instead of regex-patching.
#
# The previous in-place rewrite used an ordered set of substitutions; one of them
# (`[^"]*model\.obj` -> `model.obj`) also clobbered the visual path that an
# earlier rule had just set, so the <visual> tag ended up pointing at the LOW-POLY
# COLLISION mesh.  Renders would then show the collision hull, not the scanned
# surface.  Writing the file explicitly removes that whole class of mistake.
#
# Layout (PyBullet resolves mesh paths relative to the URDF's directory):
#   collision/model.urdf   ->  <visual>    ../visual/model.obj
#                              <collision> model.obj
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
OBJ="$REPO/assets/objects"
GSO="$WS/models/gso"

"$PY" - "$OBJ" "$GSO" <<'PY'
import os, re, sys, json
OBJ, GSO = sys.argv[1], sys.argv[2]

TEMPLATE = '''<?xml version="1.0"?>
<robot name="{name}">
  <link name="base">
    <inertial>
      <origin xyz="{ix} {iy} {iz}" />
      <mass value="{mass}" />
      <inertia ixx="{ixx}" ixy="{ixy}" ixz="{ixz}" iyy="{iyy}" iyz="{iyz}" izz="{izz}" />
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
        <mesh filename="model.obj" />
      </geometry>
    </collision>
  </link>
</robot>
'''

def parse_inertial(urdf_text):
    def grab(tag, attr=None, default="0"):
        m = re.search(rf'<{tag}([^/>]*)/?>', urdf_text)
        if not m:
            return default
        body = m.group(1)
        if attr is None:
            return body
        a = re.search(rf'{attr}="([^"]+)"', body)
        return a.group(1) if a else default
    origin = grab("origin")
    # NOTE: do NOT regex the individual axes with  {axis}="..."  -- the pattern
    # x="..." also matches INSIDE xyz="...", which silently produced a 5-element
    # origin and broke Kubric's urdf_origin_offset trait.  Read the xyz attribute
    # and split it instead.
    xyz = re.search(r'xyz="([^"]+)"', origin)
    parts = xyz.group(1).split() if xyz else []
    def comp(axis):
        idx = {"x": 0, "y": 1, "z": 2}[axis]
        return parts[idx] if len(parts) > idx else "0"
    mass = re.search(r'<mass\s+value="([^"]+)"', urdf_text)
    inr = re.search(r'<inertia([^/>]*)/?>', urdf_text)
    vals = {}
    if inr:
        for k in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz"):
            mm = re.search(rf'{k}="([^"]+)"', inr.group(1))
            vals[k] = mm.group(1) if mm else "0"
    else:
        vals = {k: "0" for k in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")}
    return {
        "ix": comp("x"), "iy": comp("y"), "iz": comp("z"),
        "mass": mass.group(1) if mass else "0.05", **vals,
    }

fixed = 0
for aid in sorted(os.listdir(OBJ)):
    d = os.path.join(OBJ, aid)
    if not aid.startswith("gso_") or not os.path.isdir(d):
        continue
    # find the GSO source that produced this asset (match by manifest source_filename)
    man = open(os.path.join(d, "asset.yaml")).read()
    m = re.search(r"source_filename:\s*(.+)", man)
    src_name = m.group(1).strip() if m else None
    src_urdf = os.path.join(GSO, src_name, "object.urdf") if src_name else None
    if not src_urdf or not os.path.isfile(src_urdf):
        print(f"  {aid}: source urdf not found ({src_name})")
        continue
    info = parse_inertial(open(src_urdf).read())
    out = TEMPLATE.format(name=src_name, **info)
    open(os.path.join(d, "collision/model.urdf"), "w").write(out)
    fixed += 1
    print(f"  {aid:<48} mass={info['mass'][:8]} visual=../visual/model.obj")

print(f"  regenerated {fixed} URDFs")
PY

echo
echo "=== verify: load in PyBullet AND confirm the visual path is the hi-poly mesh ==="
"$PY" - "$OBJ" <<'PY'
import os, sys
import pybullet as pb
OBJ = sys.argv[1]
pb.connect(pb.DIRECT)
for aid in sorted(os.listdir(OBJ)):
    if not aid.startswith("gso_"):
        continue
    u = os.path.join(OBJ, aid, "collision/model.urdf")
    txt = open(u).read()
    vis_ok = "../visual/model.obj" in txt
    col_ok = 'filename="model.obj"' in txt
    try:
        pb.loadURDF(u)
        load = "OK"
    except Exception as e:
        load = f"FAIL {str(e)[:30]}"
    print(f"  {aid:<48} load={load:<8} visual_hipoly={vis_ok} collision={col_ok}")
pb.disconnect()
PY
