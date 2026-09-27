#!/usr/bin/env bash
# ===========================================================================
# Where does the rolling body's extra energy come from?
#
# Measured: an ideal GEOM_CYLINDER on an ideal GEOM_PLANE, started at exactly
# v and omega = v/r with mu 0.36, ACCELERATES from 0.276 to 0.640 m/s over the
# clip.  Nothing in that setup can supply energy except the contact solver, so
# the suspect is the numerical contact for an ultra-light body (1.5 g).
#
# This varies ONE thing at a time:
#   mass       1.5 g / 15 g / 150 g / 1.5 kg
#   timestep   240 / 480 / 960 / 1920 Hz
#   solver iters 50 / 200
# and reports the speed ratio and the total mechanical energy ratio
# (translational + rotational, against the same quantity at t=0).  A conserving
# integrator holds that ratio at 1.000.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

"$WS/tools/conda_env/bin/python" - <<'PY'
import math
import numpy as np
import pybullet as p

R, H = 0.061581, 0.170256
MU, V0 = 0.36, 0.2703
OM0 = V0 / R
FPS = 16
N = 81

def run(mass, phys_fps, iters, label):
    SUB = phys_fps // FPS
    cid = p.connect(p.DIRECT)
    p.setGravity(0, 0, -9.81, physicsClientId=cid)
    p.setTimeStep(1.0 / phys_fps, physicsClientId=cid)
    p.setPhysicsEngineParameter(numSolverIterations=iters, physicsClientId=cid)
    fc = p.createCollisionShape(p.GEOM_PLANE, physicsClientId=cid)
    fb = p.createMultiBody(0, fc, physicsClientId=cid)
    p.changeDynamics(fb, -1, lateralFriction=MU, physicsClientId=cid)
    orn = p.getQuaternionFromEuler([math.pi/2.0, 0.0, 0.0])
    cc = p.createCollisionShape(p.GEOM_CYLINDER, radius=R, height=H, physicsClientId=cid)
    bid = p.createMultiBody(mass, cc, basePosition=[0, 0, R], baseOrientation=orn,
                            physicsClientId=cid)
    p.changeDynamics(bid, -1, lateralFriction=MU, rollingFriction=0.0,
                     spinningFriction=0.0, restitution=0.0,
                     linearDamping=0.0, angularDamping=0.0, physicsClientId=cid)
    # solid-cylinder inertia about the long axis
    I = 0.5 * mass * R * R
    p.resetBaseVelocity(bid, [V0, 0, 0], [0, OM0, 0], physicsClientId=cid)
    sp, om, zs = [], [], []
    for _f in range(N):
        for _s in range(SUB):
            p.stepSimulation(physicsClientId=cid)
        v, w = p.getBaseVelocity(bid, physicsClientId=cid)
        pos, _ = p.getBasePositionAndOrientation(bid, physicsClientId=cid)
        sp.append(math.hypot(v[0], v[1])); om.append(w[1]); zs.append(pos[2])
    sp = np.asarray(sp); om = np.asarray(om); zs = np.asarray(zs)
    E = 0.5*mass*sp**2 + 0.5*I*om**2 + mass*9.81*zs
    slip = np.where(sp/R > 1e-9, om/(sp/R), np.nan)
    mid = slice(N//4, 3*N//4)
    print(f"EN {label:30s} v_end/v0={sp[-1]/sp[0]:.4f} E_end/E0={E[-1]/E[0]:.4f} "
          f"slip_mid={np.nanmean(slip[mid]):.4f} z_drift_mm={(zs[-1]-zs[0])*1000:+.3f}")
    p.disconnect(physicsClientId=cid)

print("EN ---- mass dependence (240 Hz, 50 iters) ----")
for m, lab in ((0.0014813,"mass=1.5g"), (0.014813,"mass=15g"),
               (0.14813,"mass=148g"), (1.4813,"mass=1.48kg")):
    run(m, 240, 50, lab)

print("EN ---- timestep dependence (mass=1.5g, 50 iters) ----")
for f in (240, 480, 960, 1920):
    run(0.0014813, f, 50, f"phys_fps={f}")

print("EN ---- solver iterations (mass=1.5g, 240 Hz) ----")
for it in (50, 200, 1000):
    run(0.0014813, 240, it, f"iters={it}")

print("EN ---- combined (mass=1.5g) ----")
for f, it in ((480, 200), (960, 200), (960, 1000)):
    run(0.0014813, f, it, f"phys_fps={f} iters={it}")
print("EN DONE")
PY
echo "RC ENERGY DONE"
