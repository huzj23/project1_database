#!/usr/bin/env bash
# ===========================================================================
# Measure the floor structure inside scene.blend so the extraction band is
# chosen from data, not guessed.
#
# The environment is ONE joined mesh (313k verts), so we must isolate the floor
# by geometry.  Print, for a range of z-bands, how many faces fall in the band,
# their footprint, and their area -- then pick the band that reproduces the
# known 94.28 m^2 floor.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ENVDIR="$REPO/assets/environments/replicad_apartment"

"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$ENVDIR/visual/scene.blend" --python-expr '
import bpy, numpy as np
o = bpy.data.objects["environment"]
me = o.data
mw = np.array(o.matrix_world)
n = len(me.vertices)
co = np.empty(n*3, dtype=np.float64); me.vertices.foreach_get("co", co)
w = (co.reshape(n,3) @ mw[:3,:3].T) + mw[:3,3]
me.calc_loop_triangles()
tri = np.empty(len(me.loop_triangles)*3, dtype=np.int32)
me.loop_triangles.foreach_get("vertices", tri)
tri = tri.reshape(-1,3)
print("ENV verts=%d tris=%d" % (n, len(tri)))
print("ENV z range %.4f .. %.4f" % (w[:,2].min(), w[:,2].max()))

# face centres and areas
v0, v1, v2 = w[tri[:,0]], w[tri[:,1]], w[tri[:,2]]
cen = (v0+v1+v2)/3.0
area = 0.5*np.linalg.norm(np.cross(v1-v0, v2-v0), axis=1)
# upward-facing = normal z dominant positive
nrm = np.cross(v1-v0, v2-v0)
nn = np.linalg.norm(nrm, axis=1); nn[nn==0]=1e-12
nz = nrm[:,2]/nn
up = nz > 0.7

print()
print("  z-band (m)        faces   up-faces   footprint (m)        area(up)  m^2")
for lo, hi in [(-0.10,0.02),(-0.05,0.02),(-0.02,0.01),(-0.005,0.005),
               (-0.10,0.05),(-0.10,0.10),(-0.10,0.20),(-0.10,0.35)]:
    m = (cen[:,2]>=lo)&(cen[:,2]<hi)&up
    if m.sum()==0:
        print("  [%+.3f,%+.3f)  %6d  %6d   (none)" % (lo,hi,int(((cen[:,2]>=lo)&(cen[:,2]<hi)).sum()),0))
        continue
    x0,x1 = cen[m,0].min(), cen[m,0].max()
    y0,y1 = cen[m,1].min(), cen[m,1].max()
    print("  [%+.3f,%+.3f)  %6d  %6d   x[%6.3f,%6.3f] y[%6.3f,%6.3f]  %7.2f" % (
        lo,hi,int(((cen[:,2]>=lo)&(cen[:,2]<hi)).sum()), int(m.sum()), x0,x1,y0,y1, area[m].sum()))

print()
print("  z histogram of UPWARD faces (5 cm bins, z<1.0):")
sel = up & (cen[:,2] < 1.0)
h,e = np.histogram(cen[sel,2], bins=np.arange(-0.10,1.0,0.05))
for i,c in enumerate(h):
    if c>0:
        print("    z[%+.2f,%+.2f)  faces=%6d  area=%7.2f m^2" % (e[i],e[i+1],c, area[sel][ (cen[sel,2]>=e[i])&(cen[sel,2]<e[i+1]) ].sum()))
' 2>&1 | grep -E '^  |^ENV' | head -50
