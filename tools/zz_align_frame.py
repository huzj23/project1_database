"""Put the project generator's collision OBJ into the VISUAL's own frame.

Why: scripts/generate_collision_mesh.py imports OBJ with bpy defaults, which
rotates the imported object +90 deg about X (Blender's OBJ Y-up convention).
It then exports with axis_forward="Y", axis_up="Z", which applies no further
conversion.  Net effect for OBJ input: output = Rx(+90) * raw_file_coords.

The runtime visual for this asset is in the RAW file frame (verified from the
already-rendered dataset: the actor's rendered top above the disc top matches
the raw-frame prediction to ~1 mm and the +90-rotated prediction is 27 mm off).
So the generator's raw output would be a collision body rotated 90 deg against
the visual.  This script applies the exact inverse rotation Rx(-90), i.e.
(x, y, z) -> (x, z, -y), to vertices and normals, and rewrites the URDF with
the corrected dimensions.  Nothing else is altered.
"""
import hashlib
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
urdf = Path(sys.argv[3])
report_out = Path(sys.argv[4])

# --- read the generator output, preserving structure ------------------------
verts, normals, faces, other = [], [], [], []
for line in src.read_text().splitlines():
    if line.startswith("v "):
        verts.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("vn "):
        normals.append([float(x) for x in line.split()[1:4]])
    elif line.startswith("f "):
        faces.append(line)
    else:
        other.append(line)


def rot(v):
    """Rx(-90): (x, y, z) -> (x, z, -y)."""
    return [v[0], v[2], -v[1]]


nv = [rot(v) for v in verts]
nn = [rot(v) for v in normals]

out = []
for line in other:
    out.append(line)
for v in nv:
    out.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
for n in nn:
    out.append(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")
out.extend(faces)
dst.write_text("\n".join(out) + "\n")

lo = [min(v[i] for v in nv) for i in range(3)]
hi = [max(v[i] for v in nv) for i in range(3)]
dims = [hi[i] - lo[i] for i in range(3)]

# --- URDF, same formula as the generator -----------------------------------
x, y, z = dims
ixx = (y * y + z * z) / 12.0
iyy = (x * x + z * z) / 12.0
izz = (x * x + y * y) / 12.0
urdf.write_text(
    f"""<?xml version="1.0"?>
<robot name="collision_mesh">
  <link name="body">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="1.0"/>
      <inertia ixx="{ixx:.9f}" ixy="0" ixz="0" iyy="{iyy:.9f}" iyz="0" izz="{izz:.9f}"/>
    </inertial>
    <collision>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><mesh filename="{dst.name}" scale="1 1 1"/></geometry>
    </collision>
  </link>
</robot>
""",
    encoding="utf-8",
)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


rep = {
    "vertices": len(nv),
    "triangles": len(faces),
    "bounds": {"min": lo, "max": hi},
    "dimensions": dims,
    "bounding_radius": max((v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5 for v in nv),
    "max_xy_radius": max((v[0] ** 2 + v[1] ** 2) ** 0.5 for v in nv),
    "half_extents": [d / 2.0 for d in dims],
    "support_height": -lo[2],
    "mesh_sha256": sha256(dst),
    "simulation_sha256": sha256(urdf),
}
report_out.write_text(json.dumps(rep, indent=2) + "\n")
print("ALIGNED_REPORT=" + json.dumps(rep, indent=2))
