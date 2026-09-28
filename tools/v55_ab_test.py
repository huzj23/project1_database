"""V5.5 stage 03: decisive A/B/C test -- which mesh/setup makes a proxy fall through?

Established facts:
  * 36 engine-parameter combinations all make the bottle mesh fall through the plane;
  * a control BOX and a control SPHERE both rest on that same plane;
  * but in an earlier diagnostic the glass_a mesh DID keep contact, so it is not simply
    "meshes do not collide with planes".

So the variable is the MESH or the exact START HEIGHT. Each is tested here in isolation:

  A. bottle vhacd vs glass_a vhacd       -- is it mesh-specific?
  B. plane support vs a large box floor  -- is it plane-specific?
  C. start exactly touching vs 5 mm above -- does starting in contact make the solver miss it?
  D. compound (all parts in ONE shape) vs one body per part

Hypothesis C is the leading one: the validation placed the prop's base EXACTLY on the support
surface, and the trace shows velocity already negative at t=0 and zero contacts thereafter,
which is the signature of a missed initial contact rather than a missing collider.
"""

from __future__ import annotations

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


def merged(name: str, sub: str):
    files = sorted((PROPS / name / sub).glob("*.obj"))
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def run(V, F, *, support="plane", gap=0.0, mass=0.77, concave=False, label=""):
    cid = pb.connect(pb.DIRECT)
    try:
        pb.setGravity(0, 0, -9.81, physicsClientId=cid)
        pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                     physicsClientId=cid)
        if support == "plane":
            s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                        physicsClientId=cid)
            floor = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, SUPPORT),
                                       physicsClientId=cid)
        else:
            s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[1.0, 1.0, 0.05],
                                        physicsClientId=cid)
            floor = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, SUPPORT - 0.05),
                                       physicsClientId=cid)

        plo = V.min(axis=0)
        spawn = SUPPORT - plo[2] + gap
        flags = pb.GEOM_FORCE_CONCAVE_TRIMESH if concave else 0
        cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                     indices=F.ravel().tolist(), flags=flags,
                                     physicsClientId=cid)
        body = pb.createMultiBody(mass, cs, basePosition=(0.0, 0.0, spawn),
                                  physicsClientId=cid)
        for _ in range(int(1.2 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
        cps = pb.getContactPoints(bodyA=body, bodyB=floor, physicsClientId=cid)
        returned = float(pos[2] - spawn)
        fell = returned < -0.03
        print(f"  {label:52s} {'FELL' if fell else 'rests':>6} "
              f"d_z={returned*1000:+9.3f} mm contacts={len(cps):3d}")
        return not fell
    finally:
        pb.disconnect(cid)


def main() -> int:
    bv, bf = merged("bottle_assembly", "vhacd")
    bh, bf2 = merged("bottle_assembly", "hull")
    gv, gf = merged("glass_a", "vhacd")

    print("=== A. mesh-specific? (plane support, gap=0) ===")
    run(bv, bf, label="bottle vhacd vs plane")
    run(gv, gf, mass=0.113, label="glass_a vhacd vs plane")
    run(bh, bf2, label="bottle hull vs plane")

    print("\n=== B. plane vs box floor (bottle vhacd, gap=0) ===")
    run(bv, bf, support="box", label="bottle vhacd vs box floor")

    print("\n=== C. start height (bottle vhacd vs plane) ===")
    for gap in (0.0, 0.0001, 0.0005, 0.001, 0.002, 0.005, 0.02):
        run(bv, bf, gap=gap, label=f"bottle vhacd gap={gap*1000:.2f} mm")

    print("\n=== C2. start height (glass_a vhacd vs plane) ===")
    for gap in (0.0, 0.0005, 0.002, 0.01):
        run(gv, gf, mass=0.113, gap=gap, label=f"glass_a vhacd gap={gap*1000:.2f} mm")

    print("\n=== D. concave flag (bottle vhacd, gap=0.002) ===")
    run(bv, bf, gap=0.002, concave=True, label="bottle vhacd FORCE_CONCAVE gap=2mm")
    run(bv, bf, gap=0.002, label="bottle vhacd (hull default) gap=2mm")

    print("\n=== E. support surface sanity: does the proxy base sit FLAT? ===")
    # How many vertices lie within 1 mm of the base plane? A pointy or sparse base explains a
    # missed first contact.
    for label, (V, F) in (("bottle vhacd", (bv, bf)), ("glass_a vhacd", (gv, gf))):
        lo = V.min(axis=0)[2]
        near = np.abs(V[:, 2] - lo) < 0.001
        print(f"  {label:16s} vertices within 1 mm of base: {int(near.sum())} "
              f"of {len(V)}; base area span "
              f"x={V[near,0].ptp() if near.any() else 0:.4f} "
              f"y={V[near,1].ptp() if near.any() else 0:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
