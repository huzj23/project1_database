#!/usr/bin/env bash
# ===========================================================================
# RIGOROUS verification that a refined collision hull really ROLLS in contact
# (and is not simply free-falling, which would also give a constant velocity).
#
# For each hull it reports:
#   * the collision shape's actual vertex count as PyBullet loaded it
#   * contact-point count and normal force per frame (proves it is TOUCHING)
#   * z trajectory (a rolling body holds z ~= R; a free-falling one drops)
#   * slip ratio omega/(v/r)
#   * the CROSS-SECTION radial deviation from a circle, which is the geometric
#     quantity that causes the loss
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$REPO" <<'PY'
import sys, math, os
import numpy as np
import pybullet as p
from scipy.spatial import ConvexHull

REPO = sys.argv[1]
ASSET = REPO + "/assets/objects/gso_whey_protein_vanilla"
R, H = 0.061581, 0.170256
MASS, MU, V0 = 0.0014813296262329518, 0.36, 0.2703
OM0 = V0 / R
FPS, SUB, N = 16, 15, 81
TMP = os.environ.get("PHYCO_TMP", "/tmp")
base = os.path.join(TMP, "fh2"); os.makedirs(base, exist_ok=True)

def load_obj_verts(path):
    vs = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                a = line.split(); vs.append([float(a[1]), float(a[2]), float(a[3])])
    return np.asarray(vs, float)

def write_obj(path, V, faces=None):
    """Write a CLOSED triangle mesh.

    A bare point cloud is NOT loadable: PyBullet's URDF importer needs faces,
    and when it silently fails it leaves the body without collision geometry, so
    the "object" free-falls and a free-fall at constant horizontal velocity
    looks exactly like perfect rolling.  Every hull is therefore triangulated
    from its convex hull's own simplices.
    """
    if faces is None:
        faces = ConvexHull(V).simplices
    with open(path, "w") as fh:
        fh.write("o hull\n")
        for v in V:
            fh.write(f"v {v[0]:.9f} {v[1]:.9f} {v[2]:.9f}\n")
        for f in faces:
            fh.write("f %d %d %d\n" % (f[0]+1, f[1]+1, f[2]+1))

def write_urdf(path, objname, mass=MASS):
    with open(path, "w") as fh:
        fh.write('<?xml version="1.0"?>\n<robot name="h">\n  <link name="base">\n')
        fh.write('    <inertial><origin xyz="0 0 0" /><mass value="%.10f" />'
                 '<inertia ixx="0" ixy="0" ixz="0" iyy="0" iyz="0" izz="0" />'
                 '</inertial>\n' % mass)
        fh.write('    <visual><origin xyz="0 0 0" /><geometry>'
                 '<mesh filename="%s" /></geometry></visual>\n' % objname)
        fh.write('    <collision><origin xyz="0 0 0" /><geometry>'
                 '<mesh filename="%s" /></geometry></collision>\n' % objname)
        fh.write('  </link>\n</robot>\n')

def cross_section_deviation(V):
    """Radial deviation of the cross-section about the long (Z) axis.

    A perfect circular cross-section has zero deviation; the more polygonal it
    is, the larger this number.  Measured from vertices in the mid-length band,
    which is what actually touches the floor while rolling.
    """
    half = 0.5 * float(np.abs(V[:, 2]).max())
    W = V[np.abs(V[:, 2]) <= half]
    if len(W) < 4:
        W = V
    if len(W) < 4:
        return float("nan"), 0
    r = np.hypot(W[:, 0], W[:, 1])
    return float(r.max() - r.min()), int(len(W))

def measure(urdf, label):
    cid = p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81, physicsClientId=cid)
    p.setTimeStep(1.0/(FPS*SUB), physicsClientId=cid)
    p.setPhysicsEngineParameter(numSolverIterations=50, physicsClientId=cid)
    fc = p.createCollisionShape(p.GEOM_PLANE, physicsClientId=cid)
    fb = p.createMultiBody(0, fc, physicsClientId=cid)
    p.changeDynamics(fb, -1, lateralFriction=MU, physicsClientId=cid)
    orn = p.getQuaternionFromEuler([math.pi/2.0, 0.0, 0.0])
    bid = p.loadURDF(urdf, basePosition=[0, 0, R], baseOrientation=orn,
                     useFixedBase=False, physicsClientId=cid)
    if bid < 0:
        print(f"RV {label:20s} LOAD FAILED"); p.disconnect(physicsClientId=cid); return
    nshapes = p.getNumUserData(bid)  # not used; count via mesh data instead
    nverts = -1
    try:
        md = p.getMeshData(bid, -1, physicsClientId=cid)
        nverts = md[0]
    except Exception:
        pass
    p.changeDynamics(bid, -1, mass=MASS, lateralFriction=MU,
                     rollingFriction=0.0, spinningFriction=0.0, restitution=0.0,
                     linearDamping=0.0, angularDamping=0.0, physicsClientId=cid)
    p.resetBaseVelocity(bid, [V0, 0, 0], [0, OM0, 0], physicsClientId=cid)
    sp, om, zs, ncon, nfor = [], [], [], [], []
    for _f in range(N):
        for _s in range(SUB):
            p.stepSimulation(physicsClientId=cid)
        v, w = p.getBaseVelocity(bid, physicsClientId=cid)
        pos, _ = p.getBasePositionAndOrientation(bid, physicsClientId=cid)
        sp.append(math.hypot(v[0], v[1])); om.append(w[1]); zs.append(pos[2])
        cps = p.getContactPoints(bodyA=bid, bodyB=fb, physicsClientId=cid)
        ncon.append(len(cps))
        nfor.append(max([float(c[9]) for c in cps], default=0.0))
    sp = np.asarray(sp); om = np.asarray(om); zs = np.asarray(zs)
    ncon = np.asarray(ncon); nfor = np.asarray(nfor)
    t = np.arange(N)/FPS
    g = sp[:N//2] > 1e-5
    k = -float(np.polyfit(t[:N//2][g], np.log(sp[:N//2][g]), 1)[0]) if g.sum() > 5 else float("nan")
    slip = np.where(sp/R > 1e-9, om/(sp/R), np.nan)
    mid = slice(N//4, 3*N//4)
    print(f"RV {label:20s} collVerts={nverts:5d} v0={sp[0]:.5f} v_end={sp[-1]:.5f} "
          f"ratio={sp[-1]/sp[0]:.4f} decay_k={k:+.4f}/s slip_mid={np.nanmean(slip[mid]):.4f}")
    print(f"RV   contact_frames={int((ncon>0).sum())}/{N} mean_contacts={ncon.mean():.2f} "
          f"mean_normal={nfor.mean():.6f}N  z_first={zs[0]:.6f} z_last={zs[-1]:.6f} "
          f"z_span_mm={(zs.max()-zs.min())*1000:.3f} (R={R})")
    p.disconnect(physicsClientId=cid)

vis = load_obj_verts(ASSET + "/visual/model.obj")
cur = load_obj_verts(ASSET + "/collision/model.obj")
hv = ConvexHull(vis); hull_vis = vis[hv.vertices]
hc = ConvexHull(cur); hull_cur = cur[hc.vertices]

dev_cur, n_cur = cross_section_deviation(hull_cur)
dev_vis, n_vis = cross_section_deviation(hull_vis)
print(f"RV cross-section radial spread (mid band): current64={dev_cur:.6f} m "
      f"({n_cur} pts)  visual_hull={dev_vis:.6f} m ({n_vis} pts)")
print(f"RV support_height: current64={(-hull_cur[:,2].min()):.6f} "
      f"visual_hull={(-hull_vis[:,2].min()):.6f} visual_mesh={(-vis[:,2].min()):.6f}")

for label, V in (("current64", hull_cur), ("visual_hull", hull_vis)):
    o = os.path.join(base, f"{label}.obj"); write_obj(o, V)
    u = os.path.join(base, f"{label}.urdf"); write_urdf(u, f"{label}.obj")
    measure(u, label)

# resampled real profile at 96 angular bins (smooth cross-section, real radii)
def resample(V, nbins):
    ang = np.arctan2(V[:, 1], V[:, 0]); rad = np.hypot(V[:, 0], V[:, 1])
    idx = np.clip(((ang + math.pi)/(2*math.pi)*nbins).astype(int) % nbins, 0, nbins-1)
    out = []
    for b in range(nbins):
        m = idx == b
        if not m.any(): continue
        sel = V[m]; r = np.hypot(sel[:, 0], sel[:, 1])
        out.append(sel[np.argmax(r)]); out.append(sel[np.argmin(r)])
    return np.asarray(out)

for nb in (48, 96):
    V = resample(hull_cur, nb)
    Vh = V[ConvexHull(V).vertices]
    dev, n = cross_section_deviation(Vh)
    o = os.path.join(base, f"res{nb}.obj"); write_obj(o, Vh)
    u = os.path.join(base, f"res{nb}.urdf"); write_urdf(u, f"res{nb}.obj")
    print(f"RV resampled_{nb}: verts={len(Vh)} mid_band_pts={n} radial_spread={dev:.6f} "
          f"support_height={(-Vh[:,2].min()):.6f}")
    measure(u, f"resampled_{nb}")
PY
echo "RC RIGOROUS DONE"
