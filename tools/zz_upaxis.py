"""Determine which raw axis is 'up' for a scanned upright object.

Signals computed per candidate up-axis:
  * cross-sectional area profile (should be small at feet, peak at body)
  * bottom-slab contact: how concentrated/planar the lowest slice is
  * aspect plausibility
"""
import numpy as np

SRC = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj"

verts = []
faces = []
with open(SRC) as f:
    for line in f:
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
V = np.array(verts)
F = np.array(faces)
print(f"verts={len(V)} faces={len(F)}")

# triangle areas and centroids
a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
cent = (a + b + c) / 3.0

lo, hi = V.min(axis=0), V.max(axis=0)
print("raw AABB min", np.round(lo, 6).tolist(), "max", np.round(hi, 6).tolist())
print("raw dims    ", np.round(hi - lo, 6).tolist())

names = "XYZ"
for ax in range(3):
    other = [i for i in range(3) if i != ax]
    span = hi[ax] - lo[ax]
    print(f"\n=== candidate up = {names[ax]} (span {span:.6f}) ===")
    # area profile in 10 slabs
    edges = np.linspace(lo[ax], hi[ax], 11)
    prof = []
    for i in range(10):
        m = (cent[:, ax] >= edges[i]) & (cent[:, ax] < edges[i + 1] + 1e-9)
        prof.append(areas[m].sum())
    tot = sum(prof) or 1.0
    print("  area profile (bottom->top, % of total):",
          " ".join(f"{100*p/tot:5.1f}" for p in prof))
    # bottom 5% slab: xy spread of vertices in it
    cut = lo[ax] + 0.05 * span
    m = V[:, ax] <= cut
    sl = V[m]
    print(f"  bottom-5% slab: {m.sum()} verts")
    if len(sl) > 3:
        for o in other:
            print(f"    {names[o]} range in slab: [{sl[:,o].min():.6f}, {sl[:,o].max():.6f}]"
                  f"  (full [{lo[o]:.6f}, {hi[o]:.6f}])")
    # top 5% slab
    cut2 = hi[ax] - 0.05 * span
    m2 = V[:, ax] >= cut2
    print(f"  top-5% slab: {m2.sum()} verts")

print("\n=== centroid ===")
w = areas / areas.sum()
com = (cent * w[:, None]).sum(axis=0)
print("area-weighted COM:", np.round(com, 6).tolist())
print("AABB center      :", np.round((lo + hi) / 2, 6).tolist())
