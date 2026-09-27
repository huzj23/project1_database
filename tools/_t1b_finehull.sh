#!/usr/bin/env bash
# ===========================================================================
# Does a FINER collision hull remove the geometric rolling resistance?
#
# Measured: identical initial condition, identical friction and mass
#   cylinder (ideal)   -> slip 1.001, rolls on
#   64-vertex hull     -> slip 0.970, stops (decay 0.60 /s)
# so the loss is the POLYGONALITY of the collision hull: a 64-vertex hull is a
# ~16-gon in cross-section, so the can rocks facet to facet and every edge
# landing is an inelastic impact.
#
# This builds convex hulls of the REAL scanned visual mesh at several vertex
# counts and re-runs the identical test.  If the decay falls towards zero as the
# hull approaches the true circular cross-section, the fix is to refine the
# collision hull -- i.e. to stop mis-modelling a smooth can as a 16-gon.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== tool availability ==="
"$WS/tools/conda_env/bin/python" -c "
import importlib
for m in ('scipy','trimesh','pybullet','numpy'):
    try:
        mod=importlib.import_module(m); print('TOOL', m, getattr(mod,'__version__','?'))
    except Exception as e: print('TOOL', m, 'MISSING', type(e).__name__)
"

"$WS/tools/conda_env/bin/python" - "$REPO" <<'PY'
import sys, math, os, tempfile
import numpy as np
import pybullet as p

REPO = sys.argv[1]
ASSET = REPO + "/assets/objects/gso_whey_protein_vanilla"
R, H = 0.061581, 0.170256
MASS, MU, V0 = 0.0014813296262329518, 0.36, 0.2703
OM0 = V0 / R
FPS, SUB, N = 16, 15, 81
TMP = os.environ.get("PHYCO_TMP", "/tmp")

def load_obj_verts(path):
    vs = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                a = line.split()
                vs.append([float(a[1]), float(a[2]), float(a[3])])
    return np.asarray(vs, float)

def convex_hull(V):
    from scipy.spatial import ConvexHull
    h = ConvexHull(V)
    return V[h.vertices]

def write_hull_obj(path, V, faces=None):
    with open(path, "w") as fh:
        fh.write("o hull\n")
        for v in V:
            fh.write(f"v {v[0]:.8f} {v[1]:.8f} {v[2]:.8f}\n")
        if faces is not None:
            for f in faces:
                fh.write("f %d %d %d\n" % (f[0]+1, f[1]+1, f[2]+1))

def write_urdf(path, objname):
    with open(path, "w") as fh:
        fh.write('<?xml version="1.0"?>\n<robot name="h">\n  <link name="base">\n')
        fh.write('    <inertial><origin xyz="0 0 0" /><mass value="%.10f" />'
                 '<inertia ixx="0" ixy="0" ixz="0" iyy="0" iyz="0" izz="0" />'
                 '</inertial>\n' % MASS)
        fh.write('    <collision><origin xyz="0 0 0" /><geometry>'
                 '<mesh filename="%s" /></geometry></collision>\n' % objname)
        fh.write('  </link>\n</robot>\n')

def measure(urdf, label):
    cid = p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81, physicsClientId=cid)
    p.setTimeStep(1.0 / (FPS * SUB), physicsClientId=cid)
    p.setPhysicsEngineParameter(numSolverIterations=50, physicsClientId=cid)
    fc = p.createCollisionShape(p.GEOM_PLANE, physicsClientId=cid)
    fb = p.createMultiBody(0, fc, physicsClientId=cid)
    p.changeDynamics(fb, -1, lateralFriction=MU, physicsClientId=cid)
    orn = p.getQuaternionFromEuler([math.pi/2.0, 0.0, 0.0])
    bid = p.loadURDF(urdf, basePosition=[0, 0, R], baseOrientation=orn,
                     useFixedBase=False, physicsClientId=cid)
    p.changeDynamics(bid, -1, mass=MASS, lateralFriction=MU,
                     rollingFriction=0.0, spinningFriction=0.0, restitution=0.0,
                     linearDamping=0.0, angularDamping=0.0, physicsClientId=cid)
    p.resetBaseVelocity(bid, [V0, 0, 0], [0, OM0, 0], physicsClientId=cid)
    sp, om = [], []
    for _f in range(N):
        for _s in range(SUB):
            p.stepSimulation(physicsClientId=cid)
        v, w = p.getBaseVelocity(bid, physicsClientId=cid)
        sp.append(math.hypot(v[0], v[1])); om.append(w[1])
    sp = np.asarray(sp); om = np.asarray(om)
    t = np.arange(N)/FPS
    g = sp[:N//2] > 1e-5
    k = -float(np.polyfit(t[:N//2][g], np.log(sp[:N//2][g]), 1)[0]) if g.sum() > 5 else float("nan")
    slip = np.where(sp/R > 1e-9, om/(sp/R), np.nan)
    mid = slice(N//4, 3*N//4)
    print(f"FH {label:22s} nv={len(open(urdf).readlines()):4d} v_end={sp[-1]:.5f} "
          f"ratio={sp[-1]/sp[0]:.4f} decay_k={k:.4f}/s slip_mid={np.nanmean(slip[mid]):.3f}")
    p.disconnect(physicsClientId=cid)
    return k

# --- the real scanned visual mesh -> convex hulls at several resolutions -----
vis = load_obj_verts(ASSET + "/visual/model.obj")
print(f"FH visual mesh vertices={len(vis)}")
hull = convex_hull(vis)
print(f"FH convex hull of visual mesh: {len(hull)} vertices")
base = os.path.join(TMP, "fh")
os.makedirs(base, exist_ok=True)

# full-resolution hull
obj_full = os.path.join(base, "hull_full.obj")
write_hull_obj(obj_full, hull)
urdf_full = os.path.join(base, "hull_full.urdf")
write_urdf(urdf_full, "hull_full.obj")
measure(urdf_full, "hull_visual_full")

# the CURRENT collision hull, for reference
urdf_cur = os.path.join(base, "hull_cur.urdf")
write_urdf(urdf_cur, ASSET + "/collision/model.obj")
measure(urdf_cur, "hull_current64")

# --- subsampled hulls: pick N angular bins around the long axis -------------
# The rolling resistance is set by the CROSS-SECTION polygon, so this resamples
# the real hull's radial profile at N angular bins about the long (Z) axis,
# keeping the real min/max radius at each bin.  It is the real scanned geometry
# at a chosen angular resolution, not an invented shape.
def resample_hull(V, nbins):
    ang = np.arctan2(V[:, 1], V[:, 0])
    rad = np.hypot(V[:, 0], V[:, 1])
    idx = np.clip(((ang + math.pi) / (2*math.pi) * nbins).astype(int) % nbins, 0, nbins-1)
    out = []
    for b in range(nbins):
        m = idx == b
        if not m.any():
            continue
        sel = V[m]
        # keep both the innermost and outermost point of the bin so the hull
        # follows the real profile rather than only its outer envelope
        r = np.hypot(sel[:, 0], sel[:, 1])
        for pick in (sel[np.argmax(r)], sel[np.argmin(r)]):
            out.append(pick)
    return np.asarray(out)

for nbins in (32, 64, 128, 256):
    V = resample_hull(hull, nbins)
    Vh = convex_hull(V)
    o = os.path.join(base, f"hull_{nbins}.obj")
    write_hull_obj(o, Vh)
    u = os.path.join(base, f"hull_{nbins}.urdf")
    write_urdf(u, f"hull_{nbins}.obj")
    measure(u, f"hull_resampled_{nbins}")
print("FH DONE")
PY
echo "RC FINEHULL DONE"
