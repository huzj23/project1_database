#!/usr/bin/env bash
# ===========================================================================
# STEP 1b: extract the floor slab (z in [0.00, 0.05), 81.61 m^2, upward-facing)
# as a static collision OBJ + URDF, and register it as the map region's
# `collision: type: mesh`.
#
# This DELETES the "垃圾补丁地板": the region's 2.89 m^2 box proxy is replaced by
# the scene's own floor geometry.
#
# The extraction is done here rather than with scripts/generate_environment_
# surface_collision.py because that tool selects whole source *objects*, whereas
# our environment was joined into a single mesh.  We therefore select by
# geometry (upward-facing faces within the measured floor band) and write the
# same two artefacts that tool produces: a collision OBJ and a static URDF with
# visual=../visual/model.obj-style relative reference.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ENVDIR="$REPO/assets/environments/replicad_apartment"
OUTDIR="$ENVDIR/collision/surfaces"
mkdir -p "$OUTDIR"

"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$ENVDIR/visual/scene.blend" --python-expr "
import bpy, numpy as np, os, hashlib
o = bpy.data.objects['environment']
me = o.data
mw = np.array(o.matrix_world)
n = len(me.vertices)
co = np.empty(n*3, dtype=np.float64); me.vertices.foreach_get('co', co)
w = (co.reshape(n,3) @ mw[:3,:3].T) + mw[:3,3]
me.calc_loop_triangles()
tri = np.empty(len(me.loop_triangles)*3, dtype=np.int32)
me.loop_triangles.foreach_get('vertices', tri); tri = tri.reshape(-1,3)

v0,v1,v2 = w[tri[:,0]], w[tri[:,1]], w[tri[:,2]]
cen = (v0+v1+v2)/3.0
nrm = np.cross(v1-v0, v2-v0)
nn = np.linalg.norm(nrm, axis=1); nn[nn==0]=1e-12
up = (nrm[:,2]/nn) > 0.7

# the floor band measured in floor2_measure.sh: z in [0.00, 0.05)
keep = up & (cen[:,2] >= 0.0) & (cen[:,2] < 0.05)
faces = tri[keep]
print('FLOOR faces kept: %d of %d' % (len(faces), len(tri)))
x0,x1 = w[faces][:,0].min(), w[faces][:,0].max()
y0,y1 = w[faces][:,1].min(), w[faces][:,1].max()
print('FLOOR footprint x[%.3f,%.3f] y[%.3f,%.3f]' % (x0,x1,y0,y1))
area = 0.5*np.linalg.norm(np.cross(w[faces[:,1]]-w[faces[:,0]], w[faces[:,2]]-w[faces[:,0]]), axis=1).sum()
print('FLOOR area %.2f m^2' % area)

# weld vertices so the OBJ is compact, then write it
used = np.unique(faces)
remap = {int(v):i for i,v in enumerate(used)}
with open(os.path.join('$OUTDIR','replicad_apartment_floor.obj'),'w') as f:
    f.write('# ReplicaCAD frl_apartment floor slab, extracted by geometry\n')
    f.write('# source: visual/scene.blend, upward faces with z in [0.00,0.05)\n')
    for v in used:
        f.write('v %.6f %.6f %.6f\n' % (w[v,0], w[v,1], w[v,2]))
    for f3 in faces:
        f.write('f %d %d %d\n' % (remap[int(f3[0])]+1, remap[int(f3[1])]+1, remap[int(f3[2])]+1))
print('FLOOR wrote obj: %d verts, %d faces' % (len(used), len(faces)))
" 2>&1 | grep -E '^FLOOR'

OBJ="$OUTDIR/replicad_apartment_floor.obj"
URDF="$OUTDIR/replicad_apartment_floor.urdf"
SIZE=$(stat -c%s "$OBJ")
SHA=$(sha256sum "$OBJ" | cut -d' ' -f1)
TRI=$(( $(grep -c '^f ' "$OBJ") ))

cat > "$URDF" <<EOF
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
echo "=== extracted artefacts ==="
echo "  obj : $OBJ ($SIZE bytes, $TRI triangles)"
echo "  urdf: $URDF"
echo "  sha256: $SHA"
