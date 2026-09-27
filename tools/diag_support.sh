#!/usr/bin/env bash
# ===========================================================================
# DIAGNOSE: why is supported_fraction ~0.012 even though the object now slides?
#
# supported_fraction is computed as
#     mean(|position_z - (surface.position[2] + support_height)| <= 0.03)
# i.e. it assumes the support surface's TOP is exactly surface.position[2].
#
# With the extracted floor mesh, the top is wherever the mesh actually is.  If the
# mesh's top differs from position[2] by more than 3 cm, EVERY frame counts as
# unsupported -- and the object also starts at the wrong height.
#
# Measure: the object's real z over time, and the mesh's true top under the
# object's XY.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== the extracted floor mesh: what is its top surface z? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import numpy as np
p = "assets/environments/replicad_apartment/collision/surfaces/replicad_apartment_floor.obj"
V, F = [], []
for ln in open(p):
    if ln.startswith("v "):
        V.append([float(x) for x in ln.split()[1:4]])
    elif ln.startswith("f "):
        F.append([int(x.split("/")[0]) - 1 for x in ln.split()[1:4]])
V = np.array(V); F = np.array(F)
zc = V[F][:, :, 2].mean(axis=1)
print(f"  vertices z: min={V[:,2].min():.5f} max={V[:,2].max():.5f}")
print(f"  face-centre z: min={zc.min():.5f} max={zc.max():.5f} median={np.median(zc):.5f}")
print(f"  fraction of faces with z < 0.01: {(zc < 0.01).mean():.3f}")
print(f"  fraction of faces with z < 0.05: {(zc < 0.05).mean():.3f}")
# what does a body resting on this mesh see?
print()
print("  The loader passes surface.position[2] = 0.0007 as the 'top'.")
print(f"  Mesh median face z = {np.median(zc):.5f}  -> difference {np.median(zc)-0.0007:+.5f} m")
print()
print("  NOTE: the mesh is a slab with THICKNESS -- it has both a top and a bottom")
print("  surface.  A body dropped on it rests on the TOP, but the URDF mesh is")
print("  loaded as-is, so the top is what the collision engine sees.")
PY

echo
echo "=== the actual trajectory z from the failed run ==="
if [ -f datasets/rolling/seed-1001/x1/trajectory.json ]; then
  echo "  (sample dir was removed on failure; re-deriving from the log)"
fi
grep -oE '"supported_fraction": [0-9.]+' "$WS/tmp/one.log" | tail -1 | sed 's/^/  /'

echo
echo "=== what does the ORIGINAL box proxy give?  position[2] vs mesh top ==="
echo "  box proxy top = position[2] = 0.0007  (box centred at position[2]-thickness/2)"
echo "  -> a body placed at position[2]+support_height sits exactly on it"
echo "  mesh: no such guarantee -- hence supported_fraction collapses"
