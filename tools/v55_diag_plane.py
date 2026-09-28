"""V5.5 stage 03: why does every body fall through the support plane?

In the physical proxy validation, every body -- including the VISUAL reference mesh --
drifted 2.85 m downward, which is free fall. Since the reference falls too, this is a defect
in the test harness, not in any proxy, and it must be found before any proxy verdict is
trusted.

This isolates the cause: collision-shape creation return codes, a plain box control that must
rest, and the plane's behaviour, so the harness can be shown to work at all before it is used
to judge anything.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pybullet as pb

DT = 1.0 / 480.0
PROPS = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat/props")


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
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 physicsClientId=cid)

    SUPPORT = 0.5106

    print("=== A. plane creation, explicit normal ===")
    plane_shape = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0, 0, 1],
                                          physicsClientId=cid)
    print(f"  GEOM_PLANE shape id = {plane_shape}")
    plane = pb.createMultiBody(0, plane_shape, basePosition=[0, 0, SUPPORT],
                               physicsClientId=cid)
    print(f"  plane body id = {plane}")

    print("\n=== B. control: a 20 mm box dropped 50 mm above the plane ===")
    half = 0.01
    bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3, physicsClientId=cid)
    box = pb.createMultiBody(0.05, bs, basePosition=[0, 0, SUPPORT + half + 0.05],
                             physicsClientId=cid)
    for _ in range(int(1.5 / DT)):
        pb.stepSimulation(physicsClientId=cid)
    p, _ = pb.getBasePositionAndOrientation(box, physicsClientId=cid)
    expected = SUPPORT + half
    print(f"  box z = {p[2]:.6f}, expected {expected:.6f}, delta {(p[2]-expected)*1000:+.4f} mm")
    print(f"  control {'OK' if abs(p[2]-expected) < 0.002 else 'BROKEN -- plane not supporting'}")

    print("\n=== C. mesh creation return codes ===")
    for label, sub in (("vhacd", "vhacd"), ("hull", "hull")):
        files = sorted((PROPS / "glass_a" / sub).glob("*.obj"))
        if not files:
            print(f"  {label}: no files")
            continue
        vs, fs, off = [], [], 0
        for f in files:
            v, fc = load_obj(f)
            vs.append(v)
            fs.append(fc + off)
            off += len(v)
        V = np.vstack(vs)
        F = np.vstack(fs)
        lo = V.min(axis=0)
        shift = SUPPORT - lo[2]
        s = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                    indices=F.ravel().tolist(), physicsClientId=cid)
        print(f"  {label}: {len(F)} tri -> shape id {s} "
              f"({'OK' if s >= 0 else 'FAILED'})")
        if s < 0:
            continue
        b = pb.createMultiBody(0.113, s, basePosition=[0, 0, shift],
                               physicsClientId=cid)
        # Let it settle, then measure drift over a window.
        for _ in range(int(1.0 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p0, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        for _ in range(int(0.4 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p1, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        print(f"     after settle z={p1[2]:.6f} (spawn {shift:.6f}), "
              f"drift={math.dist(p0, p1)*1000:.4f} mm")
        cps = pb.getContactPoints(bodyA=b, physicsClientId=cid)
        print(f"     contact points = {len(cps)}")
        pb.removeBody(b, physicsClientId=cid)

    pb.disconnect(cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
