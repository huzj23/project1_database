#!/usr/bin/env bash
# ===========================================================================
# Build the refined SIDE collision geometry for gso_whey_protein_vanilla.
#
# WHY: measured with an identical initial condition (v0 = 0.2703 m/s,
# omega0 = v0/r, mu 0.36, 240 Hz, same mass):
#
#   64-vertex hull (current)  slip 0.966  decay +0.674 /s  -> STOPS
#   976-vertex hull (visual)  slip 0.996  decay -0.055 /s  -> ROLLS ON
#
# Both hulls have the same radial spread (~1.0 mm), so the loss is not the
# circularity of the profile but the FACET SIZE: a 64-vertex hull is only a
# coarse polygon in cross-section, so the can rocks facet-to-facet and every
# edge landing is an inelastic impact.  The convex hull of the real scanned
# visual mesh models the same can with small facets and does not do this.
#
# This writes that hull as a SEPARATE collision geometry (model_side.*) so the
# primary collision/model.* stays byte-identical for every other scenario.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$REPO" <<'PY'
import sys, os, math
import numpy as np
from scipy.spatial import ConvexHull

REPO = sys.argv[1]
ADIR = REPO + "/assets/objects/gso_whey_protein_vanilla"
VIS = ADIR + "/visual/model.obj"
OUT_OBJ = ADIR + "/collision/model_side.obj"
OUT_URDF = ADIR + "/collision/model_side.urdf"

def load_obj_verts(path):
    vs = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                a = line.split()
                vs.append([float(a[1]), float(a[2]), float(a[3])])
    return np.asarray(vs, dtype=np.float64)

vis = load_obj_verts(VIS)
hull = ConvexHull(vis)
V = vis[hull.vertices]
# CRITICAL: ConvexHull.simplices index the ORIGINAL array, but only the hull
# vertices are written out, so the indices MUST be remapped.  Writing them
# unremapped produces face indices past the end of the file, which makes
# PyBullet SEGFAULT while loading the URDF (observed).
remap = {int(old): new for new, old in enumerate(hull.vertices)}
F = np.asarray([[remap[int(i)] for i in tri] for tri in hull.simplices], dtype=int)
assert F.min() >= 0 and F.max() < len(V), "face index out of range"
print(f"GEN visual verts={len(vis)}  hull verts={len(V)}  faces={len(F)} "
      f"face_index_range=[{F.min()},{F.max()}]")

def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.asarray(((1.0, 0, 0), (0, c, -s), (0, s, c)))

def support_height(W):
    return float((-W[:, 2]).max())

def footprint_radius(W):
    return float(np.hypot(W[:, 0], W[:, 1]).max())

R_side = rot_x(math.pi / 2.0)
W = (R_side @ V.T).T
print(f"GEN upright: support_height={support_height(V):.9f} "
      f"footprint_radius={footprint_radius(V):.9f} "
      f"half_extents={np.round((V.max(axis=0)-V.min(axis=0))/2, 9).tolist()}")
print(f"GEN side   : support_height={support_height(W):.9f} "
      f"footprint_radius={footprint_radius(W):.9f}")

# wobble of the side support height over a full roll about the long axis
hs = []
for deg in range(0, 360, 1):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    Rz = np.asarray(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)))
    hs.append(support_height((R_side @ Rz @ V.T).T))
hs = np.asarray(hs)
print(f"GEN side wobble over roll: min={hs.min():.9f} max={hs.max():.9f} "
      f"span={hs.max()-hs.min():.9f} mean={hs.mean():.9f}")

with open(OUT_OBJ, "w") as fh:
    fh.write("o convex_side\n")
    for v in V:
        fh.write(f"v {v[0]:.9f} {v[1]:.9f} {v[2]:.9f}\n")
    for f in F:
        fh.write("f %d %d %d\n" % (f[0] + 1, f[1] + 1, f[2] + 1))
print(f"GEN wrote {OUT_OBJ} ({os.path.getsize(OUT_OBJ)} bytes)")

# Mirror the existing URDF's structure exactly so the loader sees the same shape.
with open(OUT_URDF, "w") as fh:
    fh.write('<?xml version="1.0"?>\n')
    fh.write('<robot name="Whey_Protein_Vanilla_side">\n')
    fh.write('  <link name="base">\n')
    fh.write('    <inertial>\n')
    fh.write('      <origin xyz="0 0 0" />\n')
    fh.write('      <mass value="0.0017833943411836959" />\n')
    fh.write('      <inertia ixx="0" ixy="0" ixz="0" iyy="0" iyz="0" izz="0" />\n')
    fh.write('    </inertial>\n')
    fh.write('    <visual>\n      <origin xyz="0 0 0" />\n      <geometry>\n')
    fh.write('        <mesh filename="../visual/model.obj" />\n')
    fh.write('      </geometry>\n    </visual>\n')
    fh.write('    <collision>\n      <origin xyz="0 0 0" />\n      <geometry>\n')
    fh.write('        <mesh filename="model_side.obj" />\n')
    fh.write('      </geometry>\n    </collision>\n')
    fh.write('  </link>\n</robot>\n')
print(f"GEN wrote {OUT_URDF} ({os.path.getsize(OUT_URDF)} bytes)")

# --- self-check: the written OBJ must reload as a closed mesh --------------
def reload_check(path):
    vs, nf, maxidx = [], 0, -1
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                vs.append(line.split()[1:4])
            elif line.startswith("f "):
                nf += 1
                for tok in line.split()[1:]:
                    maxidx = max(maxidx, int(tok.split("/")[0]) - 1)
    assert maxidx < len(vs), f"{path}: face index {maxidx} >= vertex count {len(vs)}"
    print(f"GEN verify {os.path.basename(path)}: verts={len(vs)} faces={nf} "
          f"max_face_index={maxidx} OK")

reload_check(OUT_OBJ)
print("GEN DONE")
PY
echo "RC GEN SIDE DONE"
