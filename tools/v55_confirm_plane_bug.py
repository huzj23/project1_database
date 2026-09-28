"""V5.5 stage 03: confirm the pybullet GEOM_MESH-vs-GEOM_PLANE limitation.

Evidence assembled:
  * a control GEOM_BOX rests on the plane, and a control GEOM_SPHERE rests on the plane;
  * the bottle proxy mesh FALLS through that same plane at every start height from 0 to 20 mm,
    with zero contacts, for the vhacd decomposition, the convex hull, and two different props;
  * the same mesh RESTS on a large GEOM_BOX floor (4 contacts).
  * In the very first diagnostic the mesh appeared to rest on the plane -- but a control box
    had been left lying at the same x/y, so the mesh was resting on the BOX, not the plane.

The reading is that GEOM_MESH does not collide with GEOM_PLANE in this pybullet build
(API 202010061, built Jan 2025). This test confirms it directly and minimally, using a
trivially convex mesh so that mesh convexity, triangle count and V-HACD quality are all
eliminated as explanations:

  * a single 20 mm cube exported as an OBJ mesh (convex, 12 triangles) dropped on a plane;
  * the same cube as a native GEOM_BOX on the same plane;
  * the same cube MESH on a large GEOM_BOX floor.

If the cube MESH falls through the plane while the cube BOX rests on it and the cube MESH
rests on the box floor, the limitation is proven and the workaround is a box floor.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pybullet as pb

DT = 1.0 / 240.0
SUPPORT = 0.5


def cube_mesh(half: float):
    v = np.array([[sx, sy, sz] for sx in (-half, half)
                  for sy in (-half, half) for sz in (-half, half)], float)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7],
                  [0, 5, 1], [0, 4, 5], [2, 3, 7], [2, 7, 6],
                  [0, 6, 2], [0, 4, 6], [1, 5, 7], [1, 7, 3]], np.int64)
    return v, f


def world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 physicsClientId=cid)
    return cid


def add_plane(cid):
    s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                physicsClientId=cid)
    return pb.createMultiBody(0, s, basePosition=(0.0, 0.0, SUPPORT), physicsClientId=cid)


def add_box_floor(cid, extent=1.0, thickness=0.05):
    s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[extent, extent, thickness],
                                physicsClientId=cid)
    return pb.createMultiBody(0, s, basePosition=(0.0, 0.0, SUPPORT - thickness),
                              physicsClientId=cid)


def settle_and_report(cid, body, floor, label, mass=0.05):
    for _ in range(int(1.5 / DT)):
        pb.stepSimulation(physicsClientId=cid)
    pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
    cps = pb.getContactPoints(bodyA=body, bodyB=floor, physicsClientId=cid)
    top_expected = SUPPORT + 0.01
    fell = pos[2] < top_expected - 0.05
    print(f"  {label:46s} {'FELL' if fell else 'RESTS':>5} "
          f"z={pos[2]:8.4f} (expect {top_expected:.4f}) contacts={len(cps)}")
    return not fell


def main() -> int:
    half = 0.01
    v, f = cube_mesh(half)
    print(f"test cube mesh: {len(v)} verts, {len(f)} triangles (trivially convex)")

    print("\n=== 1. native GEOM_BOX on GEOM_PLANE (control) ===")
    cid = world()
    pl = add_plane(cid)
    s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3, physicsClientId=cid)
    b = pb.createMultiBody(0.05, s, basePosition=(0, 0, SUPPORT + half + 0.02),
                           physicsClientId=cid)
    box_on_plane = settle_and_report(cid, b, pl, "GEOM_BOX body vs GEOM_PLANE")
    pb.disconnect(cid)

    print("\n=== 2. the SAME cube as a GEOM_MESH on GEOM_PLANE ===")
    cid = world()
    pl = add_plane(cid)
    s = pb.createCollisionShape(pb.GEOM_MESH, vertices=v.tolist(),
                                indices=f.ravel().tolist(), physicsClientId=cid)
    b = pb.createMultiBody(0.05, s, basePosition=(0, 0, SUPPORT + half + 0.02),
                           physicsClientId=cid)
    mesh_on_plane = settle_and_report(cid, b, pl, "GEOM_MESH cube vs GEOM_PLANE")
    pb.disconnect(cid)

    print("\n=== 3. the SAME cube as a GEOM_MESH on a GEOM_BOX floor ===")
    cid = world()
    fl = add_box_floor(cid)
    s = pb.createCollisionShape(pb.GEOM_MESH, vertices=v.tolist(),
                                indices=f.ravel().tolist(), physicsClientId=cid)
    b = pb.createMultiBody(0.05, s, basePosition=(0, 0, SUPPORT + half + 0.02),
                           physicsClientId=cid)
    mesh_on_box = settle_and_report(cid, b, fl, "GEOM_MESH cube vs GEOM_BOX floor")
    pb.disconnect(cid)

    print("\n=== 4. bottle proxy mesh on a GEOM_BOX floor (the real case) ===")
    props = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat/props")
    vs, fs, off = [], [], 0
    for p in sorted((props / "bottle_assembly" / "vhacd").glob("part*.obj")):
        vv, ff = [], []
        for line in p.read_text(errors="replace").splitlines():
            if line.startswith("v "):
                q = line.split()
                vv.append([float(q[1]), float(q[2]), float(q[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    ff.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
        vs.append(np.array(vv))
        fs.append(np.array(ff) + off)
        off += len(vv)
    V = np.vstack(vs)
    F = np.vstack(fs)
    cid = world()
    fl = add_box_floor(cid)
    lo = V.min(axis=0)
    spawn = SUPPORT - lo[2]
    s = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                indices=F.ravel().tolist(), physicsClientId=cid)
    b = pb.createMultiBody(0.77, s, basePosition=(0, 0, spawn), physicsClientId=cid)
    for _ in range(int(1.5 / DT)):
        pb.stepSimulation(physicsClientId=cid)
    pos, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
    cps = pb.getContactPoints(bodyA=b, bodyB=fl, physicsClientId=cid)
    print(f"  bottle vhacd mesh vs box floor: z={pos[2]:.6f} (spawn {spawn:.6f}) "
          f"contacts={len(cps)}")
    pb.disconnect(cid)

    print("\n=== CONCLUSION ===")
    print(f"  GEOM_BOX on plane        : {'RESTS' if box_on_plane else 'FELL'}")
    print(f"  GEOM_MESH on plane       : {'RESTS' if mesh_on_plane else 'FELL'}")
    print(f"  GEOM_MESH on box floor   : {'RESTS' if mesh_on_box else 'FELL'}")
    if box_on_plane and not mesh_on_plane and mesh_on_box:
        print("  -> CONFIRMED: GEOM_MESH does not collide with GEOM_PLANE in this pybullet")
        print("     build. Use a GEOM_BOX floor for mesh colliders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
