#!/usr/bin/env bash
# ===========================================================================
# FIX THE EXTRACTION: keep only genuinely flat floor faces.
#
# Why the first attempt failed (measured):
#   I kept faces whose CENTRE z was in [0, 0.05).  A large triangle spanning a
#   height change has a low centre while its surface rises elsewhere.  Ray-casting
#   the result at the placement point (0.65, -2.15) hit z = 0.084 -- 8.4 cm above
#   the floor -- so the actor rested 7.1 cm too high and supported_fraction
#   collapsed to 0.012.
#
# Correct criterion: keep a face only if ALL THREE of its vertices lie within
# 1 cm of the floor plane.  That admits only genuinely flat floor, and rejects any
#   triangle that bridges onto furniture, stairs or a wall base.
#
# Then VERIFY by ray-casting the new mesh on a grid: every hit inside the clear
# rectangle must be at the floor height.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ENVDIR="$REPO/assets/environments/replicad_apartment"
OUTDIR="$ENVDIR/collision/surfaces"

"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$ENVDIR/visual/scene.blend" --python-expr "
import bpy, numpy as np, os
o = bpy.data.objects['environment']; me = o.data
mw = np.array(o.matrix_world)
n = len(me.vertices)
co = np.empty(n*3, dtype=np.float64); me.vertices.foreach_get('co', co)
w = (co.reshape(n,3) @ mw[:3,:3].T) + mw[:3,3]
me.calc_loop_triangles()
tri = np.empty(len(me.loop_triangles)*3, dtype=np.int32)
me.loop_triangles.foreach_get('vertices', tri); tri = tri.reshape(-1,3)

v0,v1,v2 = w[tri[:,0]], w[tri[:,1]], w[tri[:,2]]
nrm = np.cross(v1-v0, v2-v0)
nn = np.linalg.norm(nrm, axis=1); nn[nn==0]=1e-12
up = (nrm[:,2]/nn) > 0.9                       # strictly horizontal
vz = np.stack([v0[:,2], v1[:,2], v2[:,2]], axis=1)
flat = vz.max(axis=1) < 0.010                  # ALL vertices near the floor
keep = up & flat
faces = tri[keep]
area = 0.5*np.linalg.norm(np.cross(w[faces[:,1]]-w[faces[:,0]], w[faces[:,2]]-w[faces[:,0]]), axis=1).sum()
print('FLAT faces kept: %d of %d' % (len(faces), len(tri)))
print('FLAT area %.2f m^2' % area)
x0,x1 = w[faces][:,0].min(), w[faces][:,0].max()
y0,y1 = w[faces][:,1].min(), w[faces][:,1].max()
z0,z1 = w[faces][:,2].min(), w[faces][:,2].max()
print('FLAT footprint x[%.3f,%.3f] y[%.3f,%.3f]  z[%.5f,%.5f]' % (x0,x1,y0,y1,z0,z1))
used = np.unique(faces); remap = {int(v):i for i,v in enumerate(used)}
with open(os.path.join('$OUTDIR','replicad_apartment_floor.obj'),'w') as f:
    f.write('# ReplicaCAD frl_apartment flat floor slab\n')
    f.write('# upward faces (n.z>0.9) whose ALL vertices are within 1 cm of the floor\n')
    for v in used:
        f.write('v %.6f %.6f %.6f\n' % (w[v,0], w[v,1], w[v,2]))
    for f3 in faces:
        f.write('f %d %d %d\n' % (remap[int(f3[0])]+1, remap[int(f3[1])]+1, remap[int(f3[2])]+1))
print('FLAT wrote %d verts %d faces' % (len(used), len(faces)))
" 2>&1 | grep -E '^FLAT'

OBJ="$OUTDIR/replicad_apartment_floor.obj"
SHA=$(sha256sum "$OBJ" | cut -d' ' -f1)
TRI=$(grep -c '^f ' "$OBJ")
echo "  obj: $(stat -c%s "$OBJ") bytes, $TRI triangles"
echo "  sha256: $SHA"

cat > "$OUTDIR/replicad_apartment_floor.urdf" <<EOF
<?xml version="1.0"?>
<robot name="replicad_apartment_floor">
  <link name="surface">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="0"/>
      <inertia ixx="0" ixy="0" ixz="0" iyy="0" iyz="0" izz="0"/>
    </inertial>
    <collision>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><mesh filename="replicad_apartment_floor.obj" scale="1 1 1"/></geometry>
    </collision>
  </link>
</robot>
EOF

echo
echo "=== update the sha256 recorded in maps.yaml ==="
"$WS/tools/conda_env/bin/python" - "$REPO/configs/maps.yaml" "$SHA" "$TRI" <<'PY'
import sys, re
p, sha, tri = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p).read()
s = re.sub(r"(mesh_sha256: )[0-9a-f]{64}", r"\g<1>" + sha, s)
s = re.sub(r"(\n              collision:\n                type: mesh\n                mesh: collision/surfaces/replicad_apartment_floor\.obj\n                simulation: collision/surfaces/replicad_apartment_floor\.urdf\n                triangles: )\d+", r"\g<1>" + tri, s)
open(p, "w").write(s)
print("  maps.yaml sha/tri updated")
PY
