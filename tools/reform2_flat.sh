#!/usr/bin/env bash
# ===========================================================================
# Is the scene floor FLAT?  If it is, a full-floor box proxy is geometrically
# exact and far cheaper than a mesh; if it is not, we need the real mesh.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$REPO/assets/environments/replicad_apartment/visual/scene.blend" \
  --python-expr '
import bpy, numpy as np
o = bpy.data.objects["environment"]
mw = np.array(o.matrix_world)
n = len(o.data.vertices)
co = np.empty(n*3, dtype=np.float64); o.data.vertices.foreach_get("co", co)
w = (co.reshape(n,3) @ mw[:3,:3].T) + mw[:3,3]
z = w[:,2]
# the floor is the big horizontal surface; take the lowest cluster
zmin = z.min()
print("  zmin = %.5f  zmax = %.5f" % (zmin, z.max()))
for tol in (0.02, 0.05, 0.10, 0.20):
    m = z < zmin + tol
    print("  verts within %.2f m of zmin: %6d   x=[%.3f,%.3f] y=[%.3f,%.3f]" % (
        tol, m.sum(), w[m,0].min(), w[m,0].max(), w[m,1].min(), w[m,1].max()))
# how flat is the main slab?  histogram of z for the lower cluster
m = z < zmin + 0.20
zs = np.sort(z[m])
print()
print("  floor cluster z distribution (n=%d):" % m.sum())
for q in (0, 5, 25, 50, 75, 95, 100):
    print("    p%-3d = %.5f" % (q, np.percentile(zs, q)))
print("  -> spread p95-p5 = %.5f m" % (np.percentile(zs,95) - np.percentile(zs,5)))
# the actual top surface we should rest on: the mode of the slab
hist, edges = np.histogram(zs, bins=40)
top_bin = np.argmax(hist)
print("  most common z (the slab surface) = %.5f" % ((edges[top_bin]+edges[top_bin+1])/2))
# check for holes: sample a grid over the footprint and see if a floor vertex is near
xs = np.linspace(w[m,0].min()+0.1, w[m,0].max()-0.1, 40)
ys = np.linspace(w[m,1].min()+0.1, w[m,1].max()-0.1, 40)
pts = w[m][:, :2]
from scipy.spatial import cKDTree
t = cKDTree(pts)
d, _ = t.query(np.array([[x,y] for x in xs for y in ys]))
print("  grid coverage: max dist to nearest floor vert = %.3f m (large => holes)" % d.max())
' 2>&1 | grep -E '^  ' | head -30
