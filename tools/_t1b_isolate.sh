#!/usr/bin/env bash
# ===========================================================================
# DECISIVE 2x2: which of {polygonal hull, scanned floor mesh} causes the
# rolling can's deceleration?
#
#   actor  = the asset's real 64-vertex convex hull  vs  a PERFECT cylinder of
#            the same radius/height/mass
#   floor  = an ideal infinite plane  vs  the real extracted floor mesh
#
# Identical initial condition (v0, omega0 = v0/r), identical mass, identical
# friction, 240 Hz for the clip duration.  If the cylinder-on-plane case holds
# constant velocity while the hull cases do not, the loss is GEOMETRIC ROLLING
# RESISTANCE of the scanned hull -- a real property of the object, not a bug in
# the scenario.  This is a standalone diagnostic; it changes nothing.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$WS/tools/conda_env/bin/python" - "$REPO" <<'PY'
import sys, math
import numpy as np
import pybullet as p

REPO = sys.argv[1]
HULL_URDF = REPO + "/assets/objects/gso_whey_protein_vanilla/collision/model.urdf"
FLOOR_URDF = (REPO + "/assets/environments/replicad_apartment/collision/surfaces/"
              "replicad_apartment_floor.urdf")
R = 0.061581          # side-on support height (cross-section radius)
H = 0.170256          # long axis length
MASS = 0.0014813296262329518
MU = 0.36
V0 = 0.2703
OM0 = V0 / R
FPS, SUB, N = 16, 15, 81

def run(label, actor, floor):
    cid = p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81, physicsClientId=cid)
    p.setTimeStep(1.0 / (FPS * SUB), physicsClientId=cid)
    p.setPhysicsEngineParameter(numSolverIterations=50, physicsClientId=cid)

    if floor == "plane":
        fc = p.createCollisionShape(p.GEOM_PLANE, physicsClientId=cid)
        fb = p.createMultiBody(0, fc, physicsClientId=cid)
        p.changeDynamics(fb, -1, lateralFriction=MU, physicsClientId=cid)
    else:
        fb = p.loadURDF(FLOOR_URDF, basePosition=[0, 0, 0], useFixedBase=True,
                        physicsClientId=cid)
        p.changeDynamics(fb, -1, lateralFriction=MU, physicsClientId=cid)

    # spin axis is +Y (travel along +X), so the long axis lies along +Y
    orn = p.getQuaternionFromEuler([math.pi / 2.0, 0.0, 0.0])
    if actor == "hull":
        bid = p.loadURDF(HULL_URDF, basePosition=[0, 0, R], baseOrientation=orn,
                         useFixedBase=False, physicsClientId=cid)
        p.changeDynamics(bid, -1, mass=MASS, lateralFriction=MU,
                         rollingFriction=0.0, spinningFriction=0.0,
                         restitution=0.0, linearDamping=0.0, angularDamping=0.0,
                         physicsClientId=cid)
    else:
        cc = p.createCollisionShape(p.GEOM_CYLINDER, radius=R, height=H,
                                    physicsClientId=cid)
        bid = p.createMultiBody(MASS, cc, basePosition=[0, 0, R],
                                baseOrientation=orn, physicsClientId=cid)
        p.changeDynamics(bid, -1, lateralFriction=MU, rollingFriction=0.0,
                         spinningFriction=0.0, restitution=0.0,
                         linearDamping=0.0, angularDamping=0.0,
                         physicsClientId=cid)
    p.resetBaseVelocity(bid, [V0, 0, 0], [0, OM0, 0], physicsClientId=cid)

    sp, om, zs = [], [], []
    for _f in range(N):
        for _s in range(SUB):
            p.stepSimulation(physicsClientId=cid)
        v, w = p.getBaseVelocity(bid, physicsClientId=cid)
        pos, _ = p.getBasePositionAndOrientation(bid, physicsClientId=cid)
        sp.append(math.hypot(v[0], v[1])); om.append(w[1]); zs.append(pos[2])
    sp = np.asarray(sp); om = np.asarray(om); zs = np.asarray(zs)
    t = np.arange(N) / FPS
    good = sp[:N//2] > 1e-5
    k = -float(np.polyfit(t[:N//2][good], np.log(sp[:N//2][good]), 1)[0]) if good.sum() > 5 else float("nan")
    vr = sp / R
    slip = np.where(vr > 1e-9, om / vr, np.nan)
    mid = slice(N//4, 3*N//4)
    print(f"ISO {label:26s} v0={sp[0]:.5f} v_end={sp[-1]:.5f} "
          f"ratio={sp[-1]/sp[0]:.4f} decay_k={k:.4f}/s "
          f"slip_mid={np.nanmean(slip[mid]):.3f} z_span_mm={(zs.max()-zs.min())*1000:.3f}")
    p.disconnect(physicsClientId=cid)

print(f"ISO R={R} H={H} mass={MASS} mu={MU} v0={V0} omega0={OM0:.4f} (v0/R)")
for actor in ("hull", "cylinder"):
    for floor in ("plane", "floor_mesh"):
        try:
            run(f"{actor}_on_{floor}", actor, floor)
        except Exception as e:
            print(f"ISO {actor}_on_{floor} ERROR {type(e).__name__}: {str(e)[:120]}")
print("ISO DONE")
PY
echo "RC ISOLATE DONE"
