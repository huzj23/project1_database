"""V5.5 stage 03: trace the exact validation code path step by step.

The harness self-check passes (a control box rests on the plane) yet every prop free-falls at
11.2 m/s with ZERO contacts, including the visual reference mesh. Since the control works and
the prop does not, the difference must be in how the prop body is created or placed. This
prints the position and contact count over time for the real prop, alongside the numbers the
validation code actually computes, so the cause is read off rather than guessed.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pybullet as pb

DT = 1.0 / 480.0
PROPS = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat/props")
SUPPORT = 0.510600


def load_obj(path: Path):
    verts, faces = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    raw = tok.split("/")[0]
                    if raw:
                        i = int(raw)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return np.asarray(verts, float), np.asarray(faces, np.int64)


def main() -> int:
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
                                 enableConeFriction=1, physicsClientId=cid)

    shape = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                    physicsClientId=cid)
    plane = pb.createMultiBody(0, shape, basePosition=(0.0, 0.0, SUPPORT),
                               physicsClientId=cid)
    print(f"plane: shape={shape} body={plane} at z={SUPPORT}")

    files = sorted((PROPS / "bottle_assembly" / "vhacd").glob("part*.obj"))
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    V = np.vstack(vs)
    F = np.vstack(fs)
    plo, phi = V.min(axis=0), V.max(axis=0)
    base_shift = SUPPORT - plo[2]
    print(f"proxy: {len(F)} tri  aabb z {plo[2]:.6f} .. {phi[2]:.6f} "
          f"(height {phi[2]-plo[2]:.6f})")
    print(f"base_shift={base_shift:.6f} -> body origin z, base lands at "
          f"{base_shift + plo[2]:.6f}")

    cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                 indices=F.ravel().tolist(), physicsClientId=cid)
    print(f"mesh collision shape id = {cs}")
    body = pb.createMultiBody(0.77, cs, basePosition=(0.0, 0.0, base_shift),
                              physicsClientId=cid)
    print(f"body id = {body}")

    print("\n=== trace: t, z, vz, contacts(any), contacts(vs plane) ===")
    for step in range(int(2.0 / DT)):
        pb.stepSimulation(physicsClientId=cid)
        if step % int(0.1 / DT) == 0:
            pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
            lin, _ = pb.getBaseVelocity(body, physicsClientId=cid)
            all_c = pb.getContactPoints(bodyA=body, physicsClientId=cid)
            plane_c = pb.getContactPoints(bodyA=body, bodyB=plane, physicsClientId=cid)
            print(f"  t={step*DT:5.2f}s z={pos[2]:9.6f} vz={lin[2]:9.4f} "
                  f"contacts_any={len(all_c):3d} contacts_plane={len(plane_c):3d}")

    print("\n=== dynamic info of the body ===")
    di = pb.getDynamicsInfo(body, -1, physicsClientId=cid)
    print(f"  mass={di[0]}  localInertiaDiagonal={di[2]}  "
          f"friction={di[1]}  restitution={di[5]}")
    print("  (an all-zero inertia diagonal makes a body unable to receive contact impulses")

    # Compare: sphere control with the same mass and start height.
    print("\n=== control: sphere of radius 5 mm, same mass, dropped from the same height ===")
    ss = pb.createCollisionShape(pb.GEOM_SPHERE, radius=0.005, physicsClientId=cid)
    sb = pb.createMultiBody(0.77, ss, basePosition=(0.3, 0.0, SUPPORT + 0.02),
                            physicsClientId=cid)
    for _ in range(int(1.5 / DT)):
        pb.stepSimulation(physicsClientId=cid)
    sp, _ = pb.getBasePositionAndOrientation(sb, physicsClientId=cid)
    print(f"  sphere z={sp[2]:.6f} expected {SUPPORT + 0.005:.6f} "
          f"-> {'rests' if abs(sp[2]-(SUPPORT+0.005))<0.002 else 'FELL'}")

    pb.disconnect(cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
