#!/usr/bin/env bash
# ===========================================================================
# Find the largest CLEAR rectangle on the scene's own floor, for placement.
#
# Why this is needed now: collision is the real floor mesh (81.61 m^2), but
# `bounds_xy` still bounds PLACEMENT (SurfaceSampler + contains_xy).  The old
# 1.7 x 1.7 m pin is far too small for rolling / constant_force, which need
# travel room.  We must widen it -- but only over floor that is actually clear,
# otherwise the object spawns inside a sofa.
#
# Method: raycast a grid straight down from above the floor and record the
# height of the first hit.  Floor hits are ~0.0007; furniture hits are higher.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ENVDIR="$REPO/assets/environments/replicad_apartment"

"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$ENVDIR/visual/scene.blend" --python-expr '
import bpy, numpy as np
from mathutils import Vector
dg = bpy.context.evaluated_depsgraph_get()
sc = bpy.context.scene
env = bpy.data.objects["environment"]

# grid over the floor footprint
xs = np.arange(-2.4, 4.4, 0.10)
ys = np.arange(-7.9, 4.6, 0.10)
X, Y = np.meshgrid(xs, ys)
origins = [Vector((float(x), float(y), 3.0)) for x, y in zip(X.ravel(), Y.ravel())]
res = sc.ray_cast(dg, origins[0], Vector((0,0,-1)))
hits = np.zeros(len(origins)); ok = np.zeros(len(origins), bool)
for i, o in enumerate(origins):
    hit, loc, nrm, idx, obj, mat = sc.ray_cast(dg, o, Vector((0,0,-1)))
    if hit:
        hits[i] = loc.z; ok[i] = True
H = hits.reshape(X.shape); OK = ok.reshape(X.shape)
# clear = first hit is the floor itself (z < 5 cm)
clear = OK & (H < 0.05)
print("GRID points=%d  clear=%d (%.1f%%)" % (clear.size, clear.sum(), 100*clear.mean()))
print("GRID floor footprint x[%.2f,%.2f] y[%.2f,%.2f]" % (xs.min(), xs.max(), ys.min(), ys.max()))

# largest all-clear axis-aligned rectangle (brute force over row/col ranges)
best = (0, 0, 0, 0, 0)
ny, nx = clear.shape
# integral image for fast rectangle sums
I = np.zeros((ny+1, nx+1), np.int64)
I[1:,1:] = np.cumsum(np.cumsum(clear.astype(np.int64), 0), 1)
def rectsum(r0,r1,c0,c1):
    return I[r1+1,c1+1]-I[r0,c1+1]-I[r1+1,c0]+I[r0,c0]
for r0 in range(ny):
    for r1 in range(r0, ny):
        for c0 in range(nx):
            for c1 in range(c0, nx):
                area = (r1-r0+1)*(c1-c0+1)
                if area <= best[0]:
                    continue
                if rectsum(r0,r1,c0,c1) == area:
                    best = (area, r0, r1, c0, c1)
area, r0, r1, c0, c1 = best
print("BEST clear rectangle: %.1f x %.1f m = %.2f m^2" % (
    (xs[c1]-xs[c0]), (ys[r1]-ys[r0]), (xs[c1]-xs[c0])*(ys[r1]-ys[r0])))
print("BEST bounds_xy = [%.2f, %.2f, %.2f, %.2f]" % (xs[c0], xs[c1], ys[r0], ys[r1]))
' 2>&1 | grep -E '^GRID|^BEST'
