#!/usr/bin/env bash
# ===========================================================================
# Measure the gso_whey_protein_vanilla collision hull:
#   * upright vs side-on support height / footprint radius
#   * the ROLL WOBBLE: how the support height varies as the can rolls
#   * hull-vs-visual alignment (does the visual can float or sink?)
# Pure geometry, no physics, no render.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ASSET="$REPO/assets/objects/gso_whey_protein_vanilla"

"$WS/tools/conda_env/bin/python" - "$ASSET" <<'PY'
import sys, math
import numpy as np

ASSET = sys.argv[1]

def load_obj(path):
    vs = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                vs.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return np.asarray(vs, dtype=np.float64)

hull = load_obj(ASSET + "/collision/model.obj")
vis = load_obj(ASSET + "/visual/model.obj")

def report(name, V):
    mn, mx = V.min(axis=0), V.max(axis=0)
    print(f"GEOM {name}: n={len(V)}")
    print(f"GEOM {name} min={np.round(mn,6).tolist()} max={np.round(mx,6).tolist()}")
    print(f"GEOM {name} dim={np.round(mx-mn,6).tolist()} centre={np.round((mn+mx)/2,6).tolist()}")
    print(f"GEOM {name} support_height(upright)=max(-z)={(-mn[2]):.6f}")
    print(f"GEOM {name} footprint_radius(upright)={np.hypot(V[:,0],V[:,1]).max():.6f}")
    print(f"GEOM {name} bounding_radius={np.linalg.norm(V,axis=1).max():.6f}")

report("hull", hull)
report("visual", vis)

def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1,0,0],[0,c,-s],[0,s,c]])
def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]])

def support_height(V, R):
    """z the ORIGIN must sit at for the lowest rotated vertex to touch z=0."""
    return float((-(R @ V.T)[2]).max())

def footprint_radius(V, R):
    W = (R @ V.T).T
    return float(np.hypot(W[:,0], W[:,1]).max())

# ---- side orientation used by the scenario: long axis (local Z) horizontal ----
# R_base = Rz(phi) @ Rx(+90deg) maps local Z -> -Y then yaws -Y onto the roll axis.
def side_base(axis_xy):
    ax, ay = axis_xy
    n = math.hypot(ax, ay)
    ax, ay = ax/n, ay/n
    phi = math.atan2(ax, -ay)
    return rot_z(phi) @ rot_x(math.pi/2.0)

for axis, label in ((( 0.0, 1.0), "axis=+Y (travel +X)"),
                    (( 1.0, 0.0), "axis=+X (travel +Y)"),
                    ((-0.1736, 0.9848), "axis perp to +10deg travel")):
    R = side_base(axis)
    print(f"GEOM side {label}: support_height={support_height(hull,R):.6f} "
          f"footprint_radius={footprint_radius(hull,R):.6f}")
    # long axis really horizontal?
    zaxis = R @ np.array([0.0, 0.0, 1.0])
    print(f"GEOM side {label}: local Z -> world {np.round(zaxis,6).tolist()} (|z|={abs(zaxis[2]):.2e})")
    yaxis = R @ np.array([0.0, 1.0, 0.0])
    print(f"GEOM side {label}: local Y -> world {np.round(yaxis,6).tolist()}")

# ---- wobble: support height as a function of ROLL angle about the long axis ----
R0 = side_base((0.0, 1.0))
hs = []
for deg in range(0, 360, 2):
    R = R0 @ rot_z(math.radians(deg))
    hs.append(support_height(hull, R))
hs = np.asarray(hs)
print(f"GEOM wobble over roll angle: min={hs.min():.6f} max={hs.max():.6f} "
      f"span={hs.max()-hs.min():.6f} mean={hs.mean():.6f} std={hs.std():.6f}")
print(f"GEOM wobble samples deg=0..30: {np.round(hs[:16],6).tolist()}")
print(f"GEOM upright support_height declared=0.082322 measured={(-hull[:,2].min()):.6f}")
print(f"GEOM side  support_height candidate A (max over roll)={hs.max():.6f}")
print(f"GEOM side  support_height candidate B (declared footprint_radius)=0.061148")
print(f"GEOM side  support_height candidate C (half_extents y)=0.061014")
print("GEOM DONE")
PY
echo "RC GEOM DONE"
